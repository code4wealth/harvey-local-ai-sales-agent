"""The ONE AI path in this application.

Every AI inference call in Harvey Local goes through this module, which talks
ONLY to a local Ollama server at http://127.0.0.1:11434. There is no
configuration override and no cloud fallback. If Ollama is down, callers get
OllamaUnavailable and should queue the task (see app/queue_worker.py).

app/research/ may touch the internet but must never import this module. This
module may receive researched text as input, but must never import research.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app import db as _db

# Hard-coded by design. Do not read this value from environment/configuration.
OLLAMA_URL = "http://127.0.0.1:11434"

logger = logging.getLogger("harvey.llm")
DEFAULT_TIMEOUT = 180.0
UP_TIMEOUT = 2.0


class OllamaError(Exception):
    """Base class for local Ollama errors."""


class OllamaUnavailable(OllamaError):
    """The local server could not be reached because of a connection error or timeout."""


class OllamaResponseError(OllamaError):
    """Ollama responded, but its status or response body was unusable."""


class ModelNotPulled(OllamaResponseError):
    """The requested model is missing from the local Ollama server."""


class InvalidJsonResponse(OllamaResponseError):
    """The model did not return JSON matching the requested schema after retries."""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove Qwen3-style <think>...</think> blocks from generated content."""
    return _THINK_RE.sub("", text).strip()


def _client(timeout: float) -> httpx.Client:
    """Create a client fixed to the local Ollama endpoint.

    Tests replace this factory with clients backed by httpx.MockTransport; the
    application has no mock/demo mode and always uses the fixed local URL.
    """
    return httpx.Client(base_url=OLLAMA_URL, timeout=timeout, trust_env=False)


def _unavailable(exc: httpx.HTTPError) -> OllamaUnavailable:
    return OllamaUnavailable(
        f"Ollama is not reachable at {OLLAMA_URL} ({type(exc).__name__}). "
        "Start it with `ollama serve`."
    )


def ollama_up(timeout: float = UP_TIMEOUT) -> bool:
    """Probe local ``/api/tags`` with a short timeout.

    Only connection errors and timeouts mean "down". Other unexpected
    transport failures are not hidden.
    """
    try:
        with _client(timeout) as client:
            response = client.get("/api/tags")
    except (httpx.ConnectError, httpx.TimeoutException):
        return False
    return response.status_code == 200


def ollama_version(timeout: float = UP_TIMEOUT) -> dict[str, Any]:
    """Return the local Ollama ``/api/version`` JSON or raise a typed error."""
    try:
        with _client(timeout) as client:
            response = client.get("/api/version")
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise _unavailable(exc) from exc
    if response.status_code != 200:
        raise OllamaResponseError(
            f"Ollama /api/version returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise OllamaResponseError(f"Ollama /api/version returned invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise OllamaResponseError("Ollama /api/version response must be a JSON object")
    return body


def _resolve_model(model: str | None) -> str:
    if model:
        return model
    configured = os.environ.get("DEFAULT_MODEL", "").strip()
    if configured:
        return configured
    from app.hardware import detect

    return detect().recommended_model


def _write_inference_log(
    *, task: str, model: str, prompt_tokens: int, eval_tokens: int, seconds: float
) -> None:
    """Persist exactly one row for each attempted ``/api/chat`` request.

    Logging failures intentionally propagate instead of pretending the
    inference is fully traceable when it is not.
    """
    conn = _db.connect()
    try:
        _db.log_inference(
            conn,
            task=task,
            model=model,
            host=OLLAMA_URL,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
        )
    finally:
        conn.close()


def _response_metrics(body: Any, wall_seconds: float) -> tuple[int, int, float]:
    if not isinstance(body, dict):
        return 0, 0, wall_seconds
    prompt_tokens = body.get("prompt_eval_count")
    eval_tokens = body.get("eval_count")
    total_duration = body.get("total_duration")
    seconds = (
        float(total_duration) / 1_000_000_000
        if isinstance(total_duration, (int, float)) and total_duration >= 0
        else wall_seconds
    )
    return int(prompt_tokens or 0), int(eval_tokens or 0), seconds


def chat(
    prompt: str,
    *,
    model: str | None = None,
    task: str = "manual",
    format: dict | None = None,
    system: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Make one non-streaming local Ollama chat call and return its content.

    ``format`` accepts a Pydantic ``model_json_schema()`` dictionary, which is
    passed directly to Ollama. The Qwen3 ``think`` option is always false at
    the top level of the request. Connection errors and all HTTPX timeout
    subclasses become OllamaUnavailable; other errors are not swallowed.
    """
    resolved_model = _resolve_model(model)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
        "think": False,
    }
    if format is not None:
        payload["format"] = format

    started = time.monotonic()
    try:
        with _client(timeout) as client:
            response = client.post("/api/chat", json=payload)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        elapsed = time.monotonic() - started
        _write_inference_log(
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=elapsed,
        )
        raise _unavailable(exc) from exc

    wall_seconds = time.monotonic() - started
    # Log every HTTP attempt, including model-missing / non-200 / malformed
    # responses. A failed log write is not silently ignored.
    if response.status_code == 404 and "not found" in response.text.lower():
        _write_inference_log(
            task=task, model=resolved_model, prompt_tokens=0, eval_tokens=0,
            seconds=wall_seconds,
        )
        raise ModelNotPulled(
            f"Model {resolved_model!r} is not pulled. Run: ollama pull {resolved_model}"
        )
    if response.status_code != 200:
        _write_inference_log(
            task=task, model=resolved_model, prompt_tokens=0, eval_tokens=0,
            seconds=wall_seconds,
        )
        raise OllamaResponseError(
            f"Ollama returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        _write_inference_log(
            task=task, model=resolved_model, prompt_tokens=0, eval_tokens=0,
            seconds=wall_seconds,
        )
        raise OllamaResponseError(f"Ollama returned a non-JSON body: {exc}") from exc

    prompt_tokens, eval_tokens, seconds = _response_metrics(body, wall_seconds)
    _write_inference_log(
        task=task,
        model=resolved_model,
        prompt_tokens=prompt_tokens,
        eval_tokens=eval_tokens,
        seconds=seconds,
    )
    if not isinstance(body, dict):
        raise OllamaResponseError("Ollama /api/chat response must be a JSON object")
    message = body.get("message")
    content = message.get("content", "") if isinstance(message, dict) else ""
    return strip_think(str(content))


def generate(
    prompt: str,
    *,
    model: str | None = None,
    task: str = "manual",
    system: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Plain-text generation convenience wrapper around :func:`chat`."""
    return chat(prompt, model=model, task=task, system=system, timeout=timeout)


def _extract_json(text: str) -> Any:
    """Parse JSON directly, then try the outermost JSON object/array."""
    cleaned = strip_think(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_char)
        end = cleaned.rfind(close_char)
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON object or array found in model output")


def generate_json(
    prompt: str,
    schema: type[BaseModel],
    *,
    model: str | None = None,
    task: str = "manual",
    system: str | None = None,
    retries: int = 2,
    timeout: float = DEFAULT_TIMEOUT,
) -> BaseModel:
    """Generate structured output, pass the Pydantic JSON schema to Ollama,
    validate with Pydantic, and retry invalid output twice by default.

    ``retries=2`` means up to three total inference calls. OllamaUnavailable
    and other transport/response failures propagate immediately so callers
    can queue or report the task instead of hot-looping.
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        raw = chat(
            prompt,
            model=model,
            task=task,
            format=schema.model_json_schema(),
            system=system,
            timeout=timeout,
        )
        try:
            return schema.model_validate(_extract_json(raw))
        except (ValueError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "generate_json task=%s attempt %d/%d returned invalid output: %s",
                task,
                attempt + 1,
                retries + 1,
                exc,
            )
    raise InvalidJsonResponse(
        f"Model did not return valid {schema.__name__} after {retries + 1} attempts: {last_error}"
    )
