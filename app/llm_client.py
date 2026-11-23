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
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ValidationError

from app import db as _db

# Hard-coded by design. Do not read this value from environment/configuration.
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_NUM_CTX = 4096
DEFAULT_TEMPERATURE = 0.2

logger = logging.getLogger("harvey.llm")
DEFAULT_TIMEOUT = 180.0
UP_TIMEOUT = 5.0


class OllamaError(Exception):
    """Base class for local Ollama errors."""


class OllamaUnavailable(OllamaError):
    """The local server could not be reached because of a connection error."""


class OllamaTimeout(OllamaError):
    """The local model/server did not answer before the request timed out."""


class OllamaResponseError(OllamaError):
    """Ollama responded, but its status or response body was unusable."""


class ModelNotPulled(OllamaResponseError):
    """The requested model is missing from the local Ollama server."""


class InvalidJsonResponse(OllamaResponseError):
    """The model did not return JSON matching the requested schema after retries."""


@dataclass(frozen=True)
class _ChatResult:
    content: str
    log_id: int | None


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove Qwen3-style <think>...</think> blocks from generated content."""
    return _THINK_RE.sub("", text).strip()


def clean_reply(text: str) -> str:
    """Remove reasoning and an optional enclosing Markdown code fence."""
    cleaned = strip_think(str(text)).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return fenced.group(1).strip() if fenced else cleaned


def _client(timeout: float) -> httpx.Client:
    """Create a client fixed to the local Ollama endpoint."""
    return httpx.Client(base_url=OLLAMA_URL, timeout=timeout, trust_env=False)


def _unavailable(exc: httpx.HTTPError) -> OllamaUnavailable:
    return OllamaUnavailable(
        f"Ollama is not reachable at {OLLAMA_URL} ({type(exc).__name__}). "
        "Start it with `ollama serve`."
    )


def _timed_out(model: str, timeout: float, exc: httpx.TimeoutException) -> OllamaTimeout:
    return OllamaTimeout(f"{model} did not answer within {timeout:g}s ({type(exc).__name__}).")


def ollama_up(timeout: float = UP_TIMEOUT) -> bool:
    """Probe local ``/api/tags`` with a short timeout.

    Connection failures mean unavailable. A read/write/pool timeout raises
    OllamaTimeout so status reporting can distinguish a slow server from a
    server that cannot be reached.
    """
    try:
        with _client(timeout) as client:
            response = client.get("/api/tags")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return False
    except httpx.TimeoutException as exc:
        raise OllamaTimeout(f"Ollama health probe did not answer within {timeout:g}s.") from exc
    if response.status_code != 200:
        raise OllamaResponseError(
            f"Ollama /api/tags returned HTTP {response.status_code}: {response.text[:300]}"
        )
    return True


def ollama_version(timeout: float = UP_TIMEOUT) -> dict[str, Any]:
    """Return the local Ollama ``/api/version`` JSON or raise a typed error."""
    try:
        with _client(timeout) as client:
            response = client.get("/api/version")
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise _unavailable(exc) from exc
    except httpx.TimeoutException as exc:
        raise OllamaTimeout(f"Ollama /api/version did not answer within {timeout:g}s.") from exc
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


def resolve_model_name(model: str | None = None) -> str:
    """Resolve the local model name used for an inference and its audit record."""
    return _resolve_model(model)


def _write_inference_log(
    *,
    task: str,
    model: str,
    prompt_tokens: int,
    eval_tokens: int,
    seconds: float,
    status: str,
    load_seconds: float | None = None,
) -> int:
    """Persist one request row. Success-path write errors intentionally propagate."""
    conn = _db.connect()
    try:
        return _db.log_inference(
            conn,
            task=task,
            model=model,
            host=OLLAMA_URL,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            load_seconds=load_seconds,
            status=status,
        )
    finally:
        conn.close()


def _write_error_log_best_effort(
    *,
    task: str,
    model: str,
    prompt_tokens: int,
    eval_tokens: int,
    seconds: float,
    status: str,
    load_seconds: float | None = None,
) -> int | None:
    try:
        return _write_inference_log(
            task=task,
            model=model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            load_seconds=load_seconds,
            status=status,
        )
    except Exception:
        logger.exception("could not write inference_log error row: task=%s status=%s", task, status)
        return None


def _mark_error_log_best_effort(log_id: int | None, *, task: str, status: str) -> None:
    if log_id is None:
        return
    conn = None
    try:
        conn = _db.connect()
        _db.update_inference_status(conn, log_id, status)
    except Exception:
        logger.exception("could not mark inference_log row %s as %s for task=%s", log_id, status, task)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.exception("could not close inference_log connection for row %s", log_id)


def _response_metrics(body: Any, wall_seconds: float) -> tuple[int, int, float, float | None]:
    if not isinstance(body, dict):
        return 0, 0, wall_seconds, None
    prompt_tokens = body.get("prompt_eval_count")
    eval_tokens = body.get("eval_count")
    total_duration = body.get("total_duration")
    load_duration = body.get("load_duration")
    seconds = (
        float(total_duration) / 1_000_000_000
        if isinstance(total_duration, (int, float)) and total_duration >= 0
        else wall_seconds
    )
    load_seconds = (
        float(load_duration) / 1_000_000_000
        if isinstance(load_duration, (int, float)) and load_duration >= 0
        else None
    )
    return int(prompt_tokens or 0), int(eval_tokens or 0), seconds, load_seconds


def _chat(
    prompt: str,
    *,
    model: str | None,
    task: str,
    format: dict | None,
    system: str | None,
    timeout: float,
    num_ctx: int,
) -> _ChatResult:
    if num_ctx <= 0:
        raise ValueError("num_ctx must be a positive integer")
    resolved_model = _resolve_model(model)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": DEFAULT_TEMPERATURE, "num_ctx": num_ctx},
    }
    if format is not None:
        payload["format"] = format

    started = time.monotonic()
    try:
        with _client(timeout) as client:
            response = client.post("/api/chat", json=payload)
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        elapsed = time.monotonic() - started
        _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=elapsed,
            status="error:unavailable",
        )
        raise _unavailable(exc) from exc
    except httpx.TimeoutException as exc:
        elapsed = time.monotonic() - started
        _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=elapsed,
            status="error:timeout",
        )
        raise _timed_out(resolved_model, timeout, exc) from exc

    wall_seconds = time.monotonic() - started
    if response.status_code == 404 and "not found" in response.text.lower():
        _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=wall_seconds,
            status="error:http",
        )
        raise ModelNotPulled(
            f"Model {resolved_model!r} is not pulled. Run: ollama pull {resolved_model}"
        )
    if response.status_code != 200:
        _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=wall_seconds,
            status="error:http",
        )
        raise OllamaResponseError(
            f"Ollama returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=wall_seconds,
            status="error:invalid_json",
        )
        raise OllamaResponseError(f"Ollama returned a non-JSON body: {exc}") from exc

    prompt_tokens, eval_tokens, seconds, load_seconds = _response_metrics(body, wall_seconds)
    if prompt_tokens >= 0.9 * num_ctx:
        logger.warning(
            "Ollama prompt_eval_count=%s is at least 90%% of num_ctx=%s for task=%s; "
            "the prompt may have reached the context limit.",
            prompt_tokens,
            num_ctx,
            task,
        )
    if not isinstance(body, dict):
        _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            status="error:invalid_json",
        )
        raise OllamaResponseError("Ollama /api/chat response must be a JSON object")
    message = body.get("message")
    content = message.get("content", "") if isinstance(message, dict) else ""
    content = clean_reply(str(content))

    initial_status = "ok"
    if format is not None:
        try:
            _extract_json(content)
        except ValueError:
            initial_status = "error:invalid_json"

    if initial_status == "ok":
        log_id = _write_inference_log(
            task=task,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            status="ok",
            load_seconds=load_seconds,
        )
    else:
        log_id = _write_error_log_best_effort(
            task=task,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            status=initial_status,
            load_seconds=load_seconds,
        )
    return _ChatResult(content=content, log_id=log_id)


def chat(
    prompt: str,
    *,
    model: str | None = None,
    task: str = "manual",
    format: dict | None = None,
    system: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> str:
    """Make one non-streaming local Ollama chat call and return its content.

    ``format`` accepts a Pydantic ``model_json_schema()`` dictionary, which is
    passed directly to Ollama. ``think`` is always false at the top level.
    ``num_ctx`` defaults to 4096; callers can pass
    ``hardware.detect().recommended_num_ctx`` for the detected hardware tier.
    Connection errors and connect timeouts become OllamaUnavailable. Other
    request timeouts become OllamaTimeout, and other errors are not swallowed.
    """
    return _chat(
        prompt,
        model=model,
        task=task,
        format=format,
        system=system,
        timeout=timeout,
        num_ctx=num_ctx,
    ).content


def generate(
    prompt: str,
    *,
    model: str | None = None,
    task: str = "manual",
    system: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> str:
    """Plain-text generation convenience wrapper around :func:`chat`."""
    return chat(
        prompt,
        model=model,
        task=task,
        system=system,
        timeout=timeout,
        num_ctx=num_ctx,
    )


def _extract_json(text: str) -> Any:
    """Parse JSON directly, then try the outermost JSON object/array."""
    cleaned = clean_reply(text)
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
    num_ctx: int = DEFAULT_NUM_CTX,
    post_validate: Callable[[BaseModel], None] | None = None,
) -> BaseModel:
    """Generate structured output and validate it with Pydantic.

    ``retries=2`` means up to three total inference calls. Each retry includes
    the previous schema or ``post_validate`` error. Transport/response failures
    propagate immediately so callers can queue or report the task instead of
    hot-looping.
    """
    last_error: Exception | None = None
    retry_prompt = prompt
    for attempt in range(retries + 1):
        result = _chat(
            retry_prompt,
            model=model,
            task=task,
            format=schema.model_json_schema(),
            system=system,
            timeout=timeout,
            num_ctx=num_ctx,
        )
        try:
            value = schema.model_validate(_extract_json(result.content))
            if post_validate is not None:
                post_validate(value)
            return value
        except (ValueError, ValidationError) as exc:
            last_error = exc
            _mark_error_log_best_effort(
                result.log_id, task=task, status="error:invalid_json"
            )
            logger.warning(
                "generate_json task=%s attempt %d/%d returned invalid output: %s",
                task,
                attempt + 1,
                retries + 1,
                exc,
            )
            retry_prompt = (
                prompt
                + f"\n\nYour previous answer was invalid: {last_error}. "
                "Return only valid JSON matching the schema."
            )
    raise InvalidJsonResponse(
        f"Model did not return valid {schema.__name__} after {retries + 1} attempts: {last_error}"
    )
