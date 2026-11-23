from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from app.db import list_inference_logs
from app.llm_client import (
    OLLAMA_GENERATE_URL,
    OLLAMA_TAGS_URL,
    InvalidLLMResponse,
    OllamaClient,
    OllamaModelMissing,
    OllamaUnavailable,
)


class CompanyProfile(BaseModel):
    name: str


def test_generate_uses_only_local_ollama_and_logs_usage(tmp_path):
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "response": "<think>private reasoning</think>\nHello from local Ollama.",
                "prompt_eval_count": 12,
                "eval_count": 7,
                "eval_duration": 2_000_000_000,
            },
        )

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        result = client.generate(task="profile", prompt="Summarize these local facts.")
    finally:
        client.close()

    assert result == "Hello from local Ollama."
    assert client.last_request_metadata == {
        "url": OLLAMA_GENERATE_URL,
        "host": "http://127.0.0.1:11434",
        "model": "qwen3:4b",
        "think": False,
        "format": None,
        "num_predict": 1500,
    }
    assert client.last_raw_response == "<think>private reasoning</think>\nHello from local Ollama."
    assert client.last_response_had_thinking is True
    assert requests[0].url == httpx.URL(OLLAMA_GENERATE_URL)
    payload = json.loads(requests[0].content)
    assert payload["model"] == "qwen3:4b"
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"]["num_predict"] == 1500
    logs = list_inference_logs(db_path=tmp_path / "harvey.db")
    assert len(logs) == 1
    assert logs[0]["task"] == "profile"
    assert logs[0]["host"] == "http://127.0.0.1:11434"
    assert logs[0]["prompt_tokens"] == 12
    assert logs[0]["eval_tokens"] == 7
    assert logs[0]["tokens_per_second"] == pytest.approx(3.5)
    assert logs[0]["latency_seconds"] is not None
    assert logs[0]["latency_seconds"] >= 0
    assert logs[0]["status"] == "success"


def test_generate_cleans_lone_closing_think_marker(tmp_path):
    raw = 'Let me consider the instruction first.\n</think>\n\nREADY'

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": raw, "eval_count": 5})

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        assert client.generate(task="smoke", prompt="Reply READY") == "READY"
        assert client.last_raw_response == raw
        assert client.last_response_had_thinking is True
    finally:
        client.close()


def test_generate_detects_separate_ollama_thinking_field(tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"response": "visible answer", "thinking": "hidden reasoning"},
        )

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        assert client.generate(task="test", prompt="test") == "visible answer"
        assert client.last_response_had_thinking is True
    finally:
        client.close()


def test_ollama_up_checks_local_tags_endpoint(tmp_path):
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"models": []})

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        transport=httpx.MockTransport(respond),
    )
    try:
        assert client.ollama_up() is True
    finally:
        client.close()
    assert seen[0].url == httpx.URL(OLLAMA_TAGS_URL)
    assert client.last_health_url == OLLAMA_TAGS_URL


def test_unavailable_request_is_logged_and_queued(tmp_path):
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    db_path = tmp_path / "harvey.db"
    client = OllamaClient(
        db_path=db_path,
        default_model="qwen3:4b",
        transport=httpx.MockTransport(unavailable),
    )
    try:
        with pytest.raises(OllamaUnavailable, match="127.0.0.1:11434") as raised:
            client.generate_or_queue(
                task="research",
                prompt="Summarize the saved page.",
                max_attempts=3,
            )
    finally:
        client.close()

    assert raised.value.task_id is not None
    assert "queued" in str(raised.value).lower()
    from app.db import get_task

    queued = get_task(raised.value.task_id, db_path=db_path)
    assert queued is not None
    assert queued["status"] == "queued"
    assert queued["task_type"] == "llm.generate"
    assert queued["payload"]["task"] == "research"
    assert queued["payload"]["model"] == "qwen3:4b"
    assert queued["payload"]["num_predict"] == 1500
    logs = list_inference_logs(db_path=db_path)
    assert logs[0]["status"] == "error"
    assert logs[0]["host"] == "http://127.0.0.1:11434"


def test_missing_model_error_includes_local_pull_hint(tmp_path):
    def missing_model(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'qwen3:4b' not found"})

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        default_model="qwen3:4b",
        transport=httpx.MockTransport(missing_model),
    )
    try:
        with pytest.raises(OllamaModelMissing, match="ollama pull qwen3:4b"):
            client.generate(task="profile", prompt="facts")
    finally:
        client.close()
    assert list_inference_logs(db_path=tmp_path / "harvey.db")[0]["status"] == "error"


def test_generate_json_retries_invalid_output_and_validates_schema(tmp_path):
    responses = iter(["not JSON", '<think>reasoning</think>\n{"name":"Sample Product"}'])
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"response": next(responses), "eval_count": 4})

    db_path = tmp_path / "harvey.db"
    client = OllamaClient(
        db_path=db_path,
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        profile = client.generate_json(
            task="profile",
            prompt="Return a company profile as JSON.",
            response_model=CompanyProfile,
            max_retries=1,
        )
    finally:
        client.close()

    assert profile == CompanyProfile(name="Sample Product")
    assert len(requests) == 2
    assert json.loads(requests[0].content)["format"]["type"] == "object"
    assert len(list_inference_logs(db_path=db_path)) == 2


def test_generate_json_stops_after_two_retries(tmp_path):
    calls = 0

    def invalid(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"response": "not JSON"})

    db_path = tmp_path / "harvey.db"
    client = OllamaClient(
        db_path=db_path,
        default_model="qwen3:4b",
        transport=httpx.MockTransport(invalid),
    )
    try:
        with pytest.raises(InvalidLLMResponse, match="after 3 attempt"):
            client.generate_json(
                task="profile",
                prompt="Return JSON.",
                response_model=CompanyProfile,
                max_retries=2,
            )
    finally:
        client.close()

    assert calls == 3
    assert len(list_inference_logs(db_path=db_path)) == 3


def test_json_generation_queues_when_local_ollama_is_unavailable(tmp_path):
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    db_path = tmp_path / "harvey.db"
    client = OllamaClient(
        db_path=db_path,
        default_model="qwen3:4b",
        transport=httpx.MockTransport(unavailable),
    )
    try:
        with pytest.raises(OllamaUnavailable) as raised:
            client.generate_json(
                task="profile",
                prompt="Return a product profile as JSON.",
                response_model=CompanyProfile,
            )
    finally:
        client.close()

    assert raised.value.task_id is not None
    from app.db import get_task

    queued = get_task(raised.value.task_id, db_path=db_path)
    assert queued["status"] == "queued"
    assert queued["payload"]["response_format"]["type"] == "object"


def test_generate_allows_per_call_num_predict(tmp_path):
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"response": "READY"})

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        client.generate(task="test", prompt="Reply READY.", num_predict=64)
    finally:
        client.close()

    payload = json.loads(requests[0].content)
    assert payload["options"]["num_predict"] == 64
    assert client.last_request_metadata["num_predict"] == 64


def test_generate_accepts_ollama_json_mode_string(tmp_path):
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"response": '{"status":"ok"}'})

    client = OllamaClient(
        db_path=tmp_path / "harvey.db",
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        raw = client.generate(
            task="smoke_json",
            prompt="Return a JSON object.",
            response_format="json",
        )
    finally:
        client.close()

    assert json.loads(raw) == {"status": "ok"}
    assert json.loads(requests[0].content)["format"] == "json"
    assert client.last_request_metadata["format"] == "json"
