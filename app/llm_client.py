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
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from pydantic import BaseModel, ValidationError

from app import db as _db
from app.traceability import prompt_traceability

# Hard-coded by design. Do not read this value from environment/configuration.
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_NUM_CTX = 4096
DEFAULT_TEMPERATURE = 0.0
RETRY_TEMPERATURE = 0.2
DEFAULT_SEED = 42
DEFAULT_REPEAT_PENALTY = 1.0

logger = logging.getLogger("harvey.llm")
DEFAULT_TIMEOUT = 300.0
UP_TIMEOUT = 5.0


def _resolve_timeout(timeout: float | None = None) -> float:
    """Read the configurable local Ollama request timeout in seconds."""
    raw = os.environ.get("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)) if timeout is None else timeout
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a positive number of seconds") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a positive number of seconds")
    return value


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


class ValidationFailure(ValueError):
    """A custom workflow check failure with structured retry and storage diagnostics.

    ``details`` include rejected values and, for evidence checks, the allowed
    source quotes so the model can correct its response on the single retry.
    """

    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.details = [dict(item) for item in (details or [])]


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
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = DEFAULT_SEED,
    prompt_hash: str = "",
    commit_hash: str = "",
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
            temperature=temperature,
            seed=seed,
            repeat_penalty=DEFAULT_REPEAT_PENALTY,
            prompt_hash=prompt_hash,
            commit_hash=commit_hash,
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
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = DEFAULT_SEED,
    prompt_hash: str = "",
    commit_hash: str = "",
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
            temperature=temperature,
            seed=seed,
            prompt_hash=prompt_hash,
            commit_hash=commit_hash,
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
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = DEFAULT_SEED,
    on_raw: Callable[[str], None] | None = None,
) -> _ChatResult:
    if num_ctx <= 0:
        raise ValueError("num_ctx must be a positive integer")
    resolved_model = _resolve_model(model)
    traceability = prompt_traceability(prompt)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "seed": seed,
            "repeat_penalty": DEFAULT_REPEAT_PENALTY,
            "num_ctx": num_ctx,
        },
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
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=elapsed,
            status="error:unavailable",
            temperature=temperature,
            seed=seed,
        )
        raise _unavailable(exc) from exc
    except httpx.TimeoutException as exc:
        elapsed = time.monotonic() - started
        _write_error_log_best_effort(
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=elapsed,
            status="error:timeout",
            temperature=temperature,
            seed=seed,
        )
        raise _timed_out(resolved_model, timeout, exc) from exc

    wall_seconds = time.monotonic() - started
    if response.status_code == 404 and "not found" in response.text.lower():
        _write_error_log_best_effort(
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=wall_seconds,
            status="error:http",
            temperature=temperature,
            seed=seed,
        )
        raise ModelNotPulled(
            f"Model {resolved_model!r} is not pulled. Run: ollama pull {resolved_model}"
        )
    if response.status_code != 200:
        _write_error_log_best_effort(
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=wall_seconds,
            status="error:http",
            temperature=temperature,
            seed=seed,
        )
        raise OllamaResponseError(
            f"Ollama returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        _write_error_log_best_effort(
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=0,
            eval_tokens=0,
            seconds=wall_seconds,
            status="error:invalid_json",
            temperature=temperature,
            seed=seed,
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
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            status="error:invalid_json",
            temperature=temperature,
            seed=seed,
        )
        raise OllamaResponseError("Ollama /api/chat response must be a JSON object")
    message = body.get("message")
    content = message.get("content", "") if isinstance(message, dict) else ""
    raw_reply = str(content)
    if on_raw is not None:
        on_raw(raw_reply)
    content = clean_reply(raw_reply)

    initial_status = "ok"
    if format is not None:
        try:
            _extract_json(content)
        except ValueError:
            initial_status = "error:invalid_json"

    if initial_status == "ok":
        log_id = _write_inference_log(
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            status="ok",
            load_seconds=load_seconds,
            temperature=temperature,
            seed=seed,
        )
    else:
        log_id = _write_error_log_best_effort(
            **traceability,
            task=task,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            seconds=seconds,
            status=initial_status,
            load_seconds=load_seconds,
            temperature=temperature,
            seed=seed,
        )
    return _ChatResult(content=content, log_id=log_id)


def chat(
    prompt: str,
    *,
    model: str | None = None,
    task: str = "manual",
    format: dict | None = None,
    system: str | None = None,
    timeout: float | None = None,
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
        timeout=_resolve_timeout(timeout),
        num_ctx=num_ctx,
    ).content


def generate(
    prompt: str,
    *,
    model: str | None = None,
    task: str = "manual",
    system: str | None = None,
    timeout: float | None = None,
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


def _format_diagnostic_value(value: Any, *, limit: int = 600) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        rendered = repr(value)
    if len(rendered) > limit:
        return rendered[: limit - 3] + "..."
    return rendered


def _validation_diagnostic(
    error: Exception, *, parsed_value: Any, invalid_output: str
) -> str:
    if isinstance(error, ValidationFailure) and error.details:
        reasons = []
        for detail in error.details:
            field = str(detail.get("field", "<unknown>"))
            check = str(detail.get("check", str(error)))
            value = _format_diagnostic_value(detail.get("value"))
            allowed_quotes = detail.get("allowed_quotes")
            if allowed_quotes is None:
                reasons.append(f"{field}: {check}; value={value}")
            else:
                allowed = _format_diagnostic_value(allowed_quotes)
                reasons.append(f"{field}: {check}; value={value}; allowed_quotes={allowed}")
        return f"{error}; " + " | ".join(reasons)

    if isinstance(error, ValidationError):
        reasons = []
        for detail in error.errors(include_url=False):
            path = ".".join(str(part) for part in detail.get("loc", ())) or "<root>"
            message = str(detail.get("msg", "validation failed"))
            value = _format_diagnostic_value(detail.get("input"))
            reasons.append(f"{path}: {message}; value={value}")
        if reasons:
            return "; ".join(reasons)

    if parsed_value is not None:
        return f"{error}; value={_format_diagnostic_value(parsed_value)}"
    return f"{error}; invalid_output={_format_diagnostic_value(invalid_output)}"


def generate_json(
    prompt: str,
    schema: type[BaseModel],
    *,
    model: str | None = None,
    task: str = "manual",
    system: str | None = None,
    retries: int = 1,
    timeout: float | None = None,
    num_ctx: int = DEFAULT_NUM_CTX,
    base_seed: int = DEFAULT_SEED,
    attempt_offset: int = 0,
    post_validate: Callable[[BaseModel], None] | None = None,
    retry_instruction: str | None = None,
    on_attempt_options: Callable[[dict[str, Any]], None] | None = None,
    on_raw: Callable[[str], None] | None = None,
) -> BaseModel:
    """Generate structured output and validate it with Pydantic.

    ``retries=1`` means one initial inference plus at most one validation retry.
    The first request uses temperature 0 and ``base_seed + attempt_offset``;
    the retry uses temperature 0.2 and the next seed. ``attempt_offset`` lets a
    multi-stage workflow continue the same seed/temperature sequence. The retry
    prompt includes the previous schema or ``post_validate`` error and stricter
    instructions to check every constraint and source claim. Transport/response
    failures propagate immediately so callers can queue or report the task
    instead of hot-looping. If supplied, ``retry_instruction`` adds
    workflow-specific constraints to the single retry; ``on_attempt_options``
    receives the options before each request, and ``on_raw`` receives each
    reply before cleanup.
    """
    if retries < 0 or retries > 1:
        raise ValueError("retries must be 0 or 1; at most one validation retry is allowed")
    if attempt_offset < 0:
        raise ValueError("attempt_offset must be non-negative")
    timeout = _resolve_timeout(timeout)

    last_error: Exception | None = None
    last_value: Any = None
    last_output = ""
    retry_prompt = prompt
    for attempt in range(retries + 1):
        request_number = attempt_offset + attempt
        attempt_seed = int(base_seed) + request_number
        attempt_temperature = (
            DEFAULT_TEMPERATURE if request_number == 0 else RETRY_TEMPERATURE
        )
        options = {
            "temperature": attempt_temperature,
            "seed": attempt_seed,
            "repeat_penalty": DEFAULT_REPEAT_PENALTY,
        }
        if on_attempt_options is not None:
            on_attempt_options(dict(options))
        result = _chat(
            retry_prompt,
            model=model,
            task=task,
            format=schema.model_json_schema(),
            system=system,
            timeout=timeout,
            num_ctx=num_ctx,
            temperature=attempt_temperature,
            seed=attempt_seed,
            on_raw=on_raw,
        )
        candidate_value: Any = None
        try:
            candidate_value = schema.model_validate(_extract_json(result.content))
            if post_validate is not None:
                post_validate(candidate_value)
            return candidate_value
        except (ValueError, ValidationError) as exc:
            last_error = exc
            last_value = candidate_value
            last_output = result.content
            _mark_error_log_best_effort(
                result.log_id, task=task, status="error:invalid_json"
            )
            logger.warning(
                "generate_json task=%s attempt %d/%d returned invalid output (%s)",
                task,
                request_number + 1,
                attempt_offset + retries + 1,
                type(exc).__name__,
            )
            retry_feedback = _validation_diagnostic(
                exc, parsed_value=candidate_value, invalid_output=result.content
            )
            retry_prompt = (
                prompt
                + f"\n\nYour previous answer was invalid: {retry_feedback}. "
                "This is the only retry. Correct the reported issue, follow every schema field, "
                "allowed value, range, and validation constraint exactly, and re-check every "
                "factual claim against the supplied source data. Do not invent or paraphrase "
                "source facts. Return only valid JSON matching the schema."
            )
            if retry_instruction:
                retry_prompt += f"\nAdditional workflow checks: {retry_instruction}"
    reason = (
        _validation_diagnostic(
            last_error, parsed_value=last_value, invalid_output=last_output
        )
        if last_error is not None
        else "unknown validation error"
    )
    raise InvalidJsonResponse(
        f"Model did not return valid {schema.__name__} after {retries + 1} attempts; "
        f"last validation failure: {reason}"
    ) from last_error
