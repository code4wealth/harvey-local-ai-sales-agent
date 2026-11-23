from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from app import db, llm_client
from app.llm_client import InvalidJsonResponse, OllamaUnavailable


class TinyAnswer(BaseModel):
    answer: str


def use_mock_transport(monkeypatch, handler):
    """Keep test doubles at HTTPX's transport boundary, not at chat()/LLM level."""
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


def inference_rows():
    conn = db.connect()
    try:
        return conn.execute("SELECT * FROM inference_log ORDER BY id").fetchall()
    finally:
        conn.close()


def test_fixed_url_and_think_false_schema_and_inference_log(db_path, monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"content": "<think>private reasoning</think>{\"answer\":\"hello\"}"},
                "prompt_eval_count": 11,
                "eval_count": 4,
                "total_duration": 25_000_000,
            },
        )

    use_mock_transport(monkeypatch, handler)
    result = llm_client.generate_json(
        "Return an answer.", TinyAnswer, model="qwen3:4b", task="test-structured"
    )

    assert result.answer == "hello"
    assert llm_client.OLLAMA_URL == "http://127.0.0.1:11434"
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["payload"]["think"] is False
    assert seen["payload"]["format"] == TinyAnswer.model_json_schema()
    assert seen["payload"]["model"] == "qwen3:4b"
    rows = inference_rows()
    assert len(rows) == 1
    assert rows[0]["task"] == "test-structured"
    assert rows[0]["model"] == "qwen3:4b"
    assert rows[0]["host"] == llm_client.OLLAMA_URL
    assert rows[0]["prompt_tokens"] == 11
    assert rows[0]["eval_tokens"] == 4
    assert rows[0]["seconds"] == pytest.approx(0.025)


def test_ollama_up_uses_tags_and_returns_online(db_path, monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"models": []})

    use_mock_transport(monkeypatch, handler)
    assert llm_client.ollama_up(timeout=0.1) is True
    assert paths == ["/api/tags"]


def test_invalid_json_retries_twice_after_first_attempt(db_path, monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": {"content": "not valid json"}})

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(InvalidJsonResponse):
        llm_client.generate_json(
            "Return JSON.", TinyAnswer, model="qwen3:4b", task="retry-test", retries=2
        )
    assert calls == 3
    assert len(inference_rows()) == 3


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_chat_translates_connect_errors_and_timeouts(db_path, monkeypatch, error_type):
    def handler(request):
        raise error_type("simulated local connection failure", request=request)

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(OllamaUnavailable):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="transport-down-test", timeout=0.1)
    assert len(inference_rows()) == 1


def test_ollama_up_returns_false_for_mocked_connection_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("simulated refusal", request=request)

    use_mock_transport(monkeypatch, handler)
    assert llm_client.ollama_up(timeout=0.1) is False


def test_chat_unmocked_raises_when_local_ollama_is_not_running(db_path):
    if llm_client.ollama_up(timeout=0.1):
        pytest.skip("Ollama is running on the local endpoint; unavailable case cannot be asserted")
    with pytest.raises(OllamaUnavailable):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="unmocked-down-test", timeout=0.2)
