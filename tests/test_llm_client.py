from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from conftest import mock_ollama_handler
from app import db, llm_client
from app.llm_client import InvalidJsonResponse, OllamaTimeout, OllamaUnavailable


class TinyAnswer(BaseModel):
    answer: str


def use_mock_transport(monkeypatch, handler, *, include_model_tags=True):
    """Replace only the HTTPX transport boundary used to reach local Ollama."""
    def factory(timeout):
        route = mock_ollama_handler(handler) if include_model_tags else handler
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(route),
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


def test_ollama_timeout_seconds_environment_setting_is_used(db_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "17.5")
    seen_timeouts = []

    def factory(timeout):
        seen_timeouts.append(timeout)

        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
            return httpx.Response(
                200, json={"message": {"content": '{"answer":"ok"}'}}
            )

        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)
    result = llm_client.generate_json(
        "Return an answer.", TinyAnswer, model="qwen3:4b", retries=0
    )
    assert result.answer == "ok"
    assert seen_timeouts == [llm_client.UP_TIMEOUT, 17.5]
    assert llm_client.DEFAULT_TIMEOUT == 300.0


def test_default_ollama_inference_timeout_is_300_seconds(monkeypatch):
    monkeypatch.delenv("OLLAMA_TIMEOUT_SECONDS", raising=False)

    assert llm_client._resolve_timeout() == 300.0


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "not-a-number"])
def test_invalid_ollama_timeout_configuration_is_rejected(monkeypatch, value):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="OLLAMA_TIMEOUT_SECONDS"):
        llm_client._resolve_timeout()


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
    assert seen["payload"]["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": 2048,
    }
    rows = inference_rows()
    assert len(rows) == 1
    assert rows[0]["task"] == "test-structured"
    assert rows[0]["model"] == "qwen3:4b"
    assert rows[0]["host"] == llm_client.OLLAMA_URL
    assert rows[0]["prompt_tokens"] == 11
    assert rows[0]["eval_tokens"] == 4
    assert rows[0]["seconds"] == pytest.approx(0.025)
    assert rows[0]["load_seconds"] == pytest.approx(5.0)
    assert rows[0]["temperature"] == 0.0
    assert rows[0]["seed"] == 42
    assert rows[0]["repeat_penalty"] == 1.0
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
    assert seen["payload"]["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": 10,
    }
    assert "at least 90%" in caplog.text
    assert inference_rows()[0]["load_seconds"] is None


def test_ollama_up_uses_tags_and_returns_online(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"models": []})

    use_mock_transport(monkeypatch, handler, include_model_tags=False)
    assert llm_client.ollama_up(timeout=0.1) is True
    assert paths == ["/api/tags"]


def test_list_installed_models_preserves_ollama_names_and_sorts(monkeypatch):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "Qwen3:4B"}, {"model": "llama3:8b"}, {"name": " Qwen3:4B "}]},
        )

    use_mock_transport(monkeypatch, handler, include_model_tags=False)
    assert llm_client.list_installed_models() == ["llama3:8b", "Qwen3:4B"]


def test_model_preference_uses_request_then_default_then_hardware(monkeypatch):
    from app import hardware

    monkeypatch.setattr(
        hardware,
        "detect",
        lambda: SimpleNamespace(recommended_model="qwen3:1.7b"),
    )
    monkeypatch.setenv("DEFAULT_MODEL", "qwen3:8b")
    assert llm_client.model_preference("qwen3:4b") == ("qwen3:4b", "request")
    assert llm_client.model_preference() == ("qwen3:8b", "DEFAULT_MODEL")

    monkeypatch.delenv("DEFAULT_MODEL")
    assert llm_client.model_preference() == ("qwen3:1.7b", "hardware recommendation")


def test_model_resolution_matches_installed_tag_case_insensitively():
    assert llm_client.resolve_model_name(
        "qwen3:4b", installed_models=["Qwen3:4B", "llama3:8b"]
    ) == "Qwen3:4B"


def test_model_resolution_rejects_missing_installed_tag():
    with pytest.raises(llm_client.ModelNotPulled, match="ollama pull qwen3:4b"):
        llm_client.resolve_model_name("qwen3:4b", installed_models=["qwen3:8b"])


def test_chat_never_calls_api_chat_when_model_tags_are_unavailable(db_path, monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/api/tags":
            raise httpx.ConnectError("Ollama is stopped", request=request)
        return httpx.Response(200, json={"message": {"content": "should not be used"}})

    use_mock_transport(monkeypatch, handler, include_model_tags=False)
    assert llm_client.resolve_model_name("qwen3:4b") == "qwen3:4b"
    with pytest.raises(OllamaUnavailable):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="tags-unavailable-test")

    assert paths == ["/api/tags", "/api/tags"]
    assert inference_rows() == []


def test_chat_does_not_call_api_chat_when_model_is_not_installed(db_path, monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"models": []})

    use_mock_transport(monkeypatch, handler, include_model_tags=False)
    with pytest.raises(llm_client.ModelNotPulled, match="ollama pull qwen3:4b"):
        llm_client.chat("Reply briefly.", model="qwen3:4b", task="model-not-installed-test")
    assert paths == ["/api/tags"]
    assert inference_rows() == []


def test_invalid_json_retries_once_with_strict_prompt_and_reason(db_path, monkeypatch):
    prompts = []
    options_sent = []

    def handler(request):
        payload = json.loads(request.content)
        prompts.append(payload["messages"][-1]["content"])
        options_sent.append(payload["options"])
        return httpx.Response(200, json={"message": {"content": "not valid json"}})

    use_mock_transport(monkeypatch, handler)
    with pytest.raises(InvalidJsonResponse, match="last validation failure"):
        llm_client.generate_json(
            "Return JSON.", TinyAnswer, model="qwen3:4b", task="retry-test", retries=1
        )
    assert len(prompts) == 2
    assert [options["seed"] for options in options_sent] == [42, 43]
    assert len({options["seed"] for options in options_sent}) == 2
    assert [options["temperature"] for options in options_sent] == [0.0, 0.2]
    assert all(options["repeat_penalty"] == 1.0 for options in options_sent)
    assert prompts[0] == "Return JSON."
    assert "Your previous answer was invalid:" in prompts[1]
    assert "This is the only retry." in prompts[1]
    assert "every schema field" in prompts[1]
    rows = inference_rows()
    assert len(rows) == 2
    assert all(row["status"] == "error:invalid_json" for row in rows)
    assert [(row["temperature"], row["seed"], row["repeat_penalty"]) for row in rows] == [
        (0.0, 42, 1.0),
        (0.2, 43, 1.0),
    ]


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

    use_mock_transport(monkeypatch, handler, include_model_tags=False)
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
