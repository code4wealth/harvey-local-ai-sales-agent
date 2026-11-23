from __future__ import annotations

import json
import socket

import httpx
import pytest
from pydantic import BaseModel

from app import db, llm_client
from app.llm_client import InvalidJsonResponse, OllamaTimeout, OllamaUnavailable


class TinyAnswer(BaseModel):
    answer: str


def use_mock_transport(monkeypatch, handler):
    """Replace only the HTTPX transport boundary used to reach local Ollama."""
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


def inference_rows():
    conn = db.connect()
    try:
        return conn.execute("SELECT * FROM inference_log ORDER BY id").fetchall()
    finally:
        conn.close()


def test_environment_cannot_override_local_ollama_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://203.0.113.99:9999")
    monkeypatch.setenv("OLLAMA_HOST", "http://203.0.113.98:11434")
    client = llm_client._client(timeout=0.1)
    try:
        assert str(client.base_url).rstrip("/") == "http://127.0.0.1:11434"
        assert client.trust_env is False
    finally:
        client.close()


def test_options_schema_think_stripping_and_inference_log(db_path, monkeypatch):
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
                "load_duration": 5_000_000_000,
            },
        )

    use_mock_transport(monkeypatch, handler)
    result = llm_client.generate_json(
        "Return an answer.",
        TinyAnswer,
        model="qwen3:4b",
        task="test-structured",
        num_ctx=2048,
    )

    assert result.answer == "hello"
    assert llm_client.OLLAMA_URL == "http://127.0.0.1:11434"
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["payload"]["think"] is False
    assert seen["payload"]["format"] == TinyAnswer.model_json_schema()
    assert seen["payload"]["model"] == "qwen3:4b"
    assert seen["payload"]["options"] == {"temperature": 0.2, "num_ctx": 2048}
    rows = inference_rows()
    assert len(rows) == 1
    assert rows[0]["task"] == "test-structured"
    assert rows[0]["model"] == "qwen3:4b"
    assert rows[0]["host"] == llm_client.OLLAMA_URL
    assert rows[0]["prompt_tokens"] == 11
    assert rows[0]["eval_tokens"] == 4
    assert rows[0]["seconds"] == pytest.approx(0.025)
    assert rows[0]["load_seconds"] == pytest.approx(5.0)
    assert rows[0]["status"] == "ok"


def test_generate_json_raw_callback_receives_each_reply_before_cleaning(db_path, monkeypatch):
    replies = [
        "<think>private first-attempt reasoning</think>not JSON",
        '<think>private second-attempt reasoning</think>{"answer":"hello"}',
    ]
    sent = iter(replies)
    raw_replies = []

    def handler(request):
        return httpx.Response(200, json={"message": {"content": next(sent)}})

    use_mock_transport(monkeypatch, handler)
    result = llm_client.generate_json(
        "Return an answer.",
        TinyAnswer,
        model="qwen3:4b",
        task="raw-callback-test",
        retries=1,
        on_raw=raw_replies.append,
    )

    assert result.answer == "hello"
    assert raw_replies == replies
    rows_as_text = json.dumps([dict(row) for row in inference_rows()])
    assert all(reply not in rows_as_text for reply in replies)
    assert "private first-attempt reasoning" not in rows_as_text
    assert "private second-attempt reasoning" not in rows_as_text


def test_prompt_near_context_limit_warns_and_format_is_optional(db_path, monkeypatch, caplog):
    seen = {}

    def handler(request):
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"message": {"content": "short reply"}, "prompt_eval_count": 9, "eval_count": 2},
        )

    use_mock_transport(monkeypatch, handler)
    assert llm_client.chat("Say hi.", model="qwen3:4b", num_ctx=10) == "short reply"
    assert "format" not in seen["payload"]
    assert seen["payload"]["options"] == {"temperature": 0.2, "num_ctx": 10}
    assert "at least 90%" in caplog.text
    assert inference_rows()[0]["load_seconds"] is None


def test_ollama_up_uses_tags_and_returns_online(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"models": []})

    use_mock_transport(monkeypatch, handler)
    assert llm_client.ollama_up(timeout=0.1) is True
    assert paths == ["/api/tags"]


def test_invalid_json_retries_twice_with_validation_error_and_status(db_path, monkeypatch):
    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return httpx.Response(200, json={"message": {"content": "not valid json"}})

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(InvalidJsonResponse):
        llm_client.generate_json(
            "Return JSON.", TinyAnswer, model="qwen3:4b", task="retry-test", retries=2
        )
    assert len(prompts) == 3
    assert prompts[0] == "Return JSON."
    assert "Your previous answer was invalid:" in prompts[1]
    assert "matching the schema" in prompts[2]
    rows = inference_rows()
    assert len(rows) == 3
    assert all(row["status"] == "error:invalid_json" for row in rows)


@pytest.mark.parametrize(
    ("error_type", "expected_exception", "expected_status"),
    [
        (httpx.ConnectError, OllamaUnavailable, "error:unavailable"),
        (httpx.ConnectTimeout, OllamaUnavailable, "error:unavailable"),
        (httpx.ReadTimeout, OllamaTimeout, "error:timeout"),
        (httpx.WriteTimeout, OllamaTimeout, "error:timeout"),
    ],
)
def test_chat_classifies_connection_and_timeout_errors(
    db_path, monkeypatch, error_type, expected_exception, expected_status
):
    def handler(request):
        raise error_type("simulated local request failure", request=request)

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(expected_exception):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="transport-error-test", timeout=0.1)
    rows = inference_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == expected_status
    assert rows[0]["prompt_tokens"] == 0
    assert rows[0]["eval_tokens"] == 0


def test_chat_marks_http_error(db_path, monkeypatch):
    def handler(request):
        return httpx.Response(503, text="local service error")

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(llm_client.OllamaResponseError, match="HTTP 503"):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="http-error-test")
    assert inference_rows()[0]["status"] == "error:http"


def test_error_log_write_failure_does_not_mask_unavailable(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv("DB_PATH", str(blocker / "harvey.db"))

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(OllamaUnavailable):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="log-failure-test", timeout=0.1)


def test_success_log_write_failure_is_not_silenced(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv("DB_PATH", str(blocker / "harvey.db"))

    def handler(request):
        return httpx.Response(200, json={"message": {"content": "ok"}})

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(FileExistsError):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="success-log-failure-test")


def test_ollama_up_returns_false_for_connection_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("simulated refusal", request=request)

    use_mock_transport(monkeypatch, handler)
    assert llm_client.ollama_up(timeout=0.1) is False


def test_chat_unmocked_raises_when_local_ollama_is_not_running(db_path, monkeypatch):
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    finally:
        probe.close()

    monkeypatch.setattr(llm_client, "OLLAMA_URL", f"http://127.0.0.1:{closed_port}")
    assert llm_client.ollama_up(timeout=5.0) is False
    with pytest.raises(OllamaUnavailable):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="unmocked-down-test", timeout=5.0)


def test_default_ollama_probe_timeout_is_five_seconds(monkeypatch):
    observed_timeouts = []

    def factory(timeout):
        observed_timeouts.append(timeout)
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"models": []})
            ),
        )

    monkeypatch.setattr(llm_client, "_client", factory)
    assert llm_client.ollama_up() is True
    assert observed_timeouts == [5.0]
