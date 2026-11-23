"""The application's only AI inference path: local Ollama over HTTP."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.db import (
    LOCAL_OLLAMA_HOST,
    enqueue_task,
    record_inference,
)
from app.hardware import recommend_model

OLLAMA_HOST = LOCAL_OLLAMA_HOST
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_HOST}/api/tags"
LLM_GENERATION_TASK = "llm.generate"

T = TypeVar("T", bound=BaseModel)


class OllamaUnavailable(RuntimeError):
    """Raised when the fixed local Ollama endpoint cannot serve a request."""

    def __init__(self, message: str, *, task_id: int | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id


class OllamaModelMissing(OllamaUnavailable):
    """Raised with a local model-download hint when Ollama lacks the model."""


class OllamaRequestError(RuntimeError):
    """Raised when Ollama responds but rejects a malformed inference request."""


class InvalidLLMResponse(ValueError):
    """Raised when a model response fails JSON decoding or schema validation."""


def _strip_thinking(text: str) -> str:
    """Remove Qwen-style thinking blocks without changing other response text."""
    return re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(body, dict):
        return str(body.get("error", body))[:500]
    return str(body)[:500]


class OllamaClient:
    """Synchronous Ollama client pinned to ``127.0.0.1:11434``.

    The optional HTTP transport exists for deterministic tests. Request URLs and
    the host written to inference logs remain fixed regardless of that transport.
    """

    def __init__(
        self,
        *,
        db_path: str | os.PathLike[str] | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
        default_model: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.default_model = default_model
        self.last_health_url: str | None = None
        self.last_request_metadata: dict[str, Any] | None = None
        self.last_response_had_thinking: bool | None = None
        self._http = httpx.Client(transport=transport, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _resolve_model(self, model: str | None) -> str:
        selected = (model or os.environ.get("DEFAULT_MODEL") or self.default_model or "").strip()
        if selected:
            return selected
        return recommend_model().model

    def ollama_up(self) -> bool:
        """Return whether the local Ollama server responds to its tags endpoint."""
        self.last_health_url = OLLAMA_TAGS_URL
        try:
            response = self._http.get(OLLAMA_TAGS_URL)
        except httpx.HTTPError:
            return False
        self.last_health_url = str(response.request.url)
        return response.is_success

    def _log(
        self,
        *,
        task: str,
        model: str,
        started: float,
        status: str,
        prompt_tokens: int | None = None,
        eval_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        record_inference(
            task=task,
            model=model,
            host=OLLAMA_HOST,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            latency_seconds=max(0.0, time.perf_counter() - started),
            status=status,
            error=error,
            db_path=self.db_path,
        )

    def generate(
        self,
        *,
        task: str,
        prompt: str,
        model: str | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> str:
        """Generate text using only the configured local Ollama endpoint."""
        if not task.strip():
            raise ValueError("Inference task must not be blank.")
        selected_model = self._resolve_model(model)
        payload: dict[str, Any] = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
        }
        if response_format is not None:
            payload["format"] = response_format

        self.last_request_metadata = {
            "url": OLLAMA_GENERATE_URL,
            "host": OLLAMA_HOST,
            "model": selected_model,
            "think": False,
            "format": response_format,
        }
        self.last_response_had_thinking = None
        started = time.perf_counter()
        prompt_tokens: int | None = None
        eval_tokens: int | None = None
        try:
            response = self._http.post(OLLAMA_GENERATE_URL, json=payload)
            self.last_request_metadata["url"] = str(response.request.url)
            if not response.is_success:
                detail = _error_text(response)
                if response.status_code == 404 and "model" in detail.lower() and "not found" in detail.lower():
                    raise OllamaModelMissing(
                        f"Ollama does not have model '{selected_model}'. Pull it locally with: ollama pull {selected_model}"
                    )
                if response.status_code >= 500 or response.status_code in {408, 429}:
                    raise OllamaUnavailable(
                        f"Ollama at {OLLAMA_HOST} returned HTTP {response.status_code}: {detail}"
                    )
                raise OllamaRequestError(
                    f"Ollama rejected the inference request (HTTP {response.status_code}): {detail}"
                )
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("response"), str):
                raise OllamaRequestError("Ollama returned a response without generated text.")
            prompt_tokens = _optional_int(data.get("prompt_eval_count"))
            eval_tokens = _optional_int(data.get("eval_count"))
            raw_result = data["response"]
            separate_thinking = data.get("thinking")
            self.last_response_had_thinking = bool(
                re.search(r"<think\b|</think\s*>", raw_result, flags=re.IGNORECASE)
                or (isinstance(separate_thinking, str) and separate_thinking.strip())
            )
            result = _strip_thinking(raw_result)
        except OllamaUnavailable as exc:
            self._log(
                task=task,
                model=selected_model,
                started=started,
                status="error",
                prompt_tokens=prompt_tokens,
                eval_tokens=eval_tokens,
                error=str(exc),
            )
            raise
        except OllamaRequestError as exc:
            self._log(
                task=task,
                model=selected_model,
                started=started,
                status="error",
                prompt_tokens=prompt_tokens,
                eval_tokens=eval_tokens,
                error=str(exc),
            )
            raise
        except (httpx.HTTPError, ValueError) as exc:
            message = f"Ollama is unavailable at {OLLAMA_HOST}. Start it with 'ollama serve' and retry."
            unavailable = OllamaUnavailable(message)
            self._log(
                task=task,
                model=selected_model,
                started=started,
                status="error",
                prompt_tokens=prompt_tokens,
                eval_tokens=eval_tokens,
                error=f"{message} ({exc})",
            )
            raise unavailable from exc

        self._log(
            task=task,
            model=selected_model,
            started=started,
            status="success",
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
        )
        return result

    def generate_json(
        self,
        *,
        task: str,
        prompt: str,
        response_model: type[T],
        model: str | None = None,
        max_retries: int = 2,
    ) -> T:
        """Generate JSON and validate it, retrying invalid output at most twice."""
        if max_retries < 0 or max_retries > 2:
            raise ValueError("max_retries must be between zero and two.")
        schema = response_model.model_json_schema()
        current_prompt = prompt
        validation_error = ""
        for attempt in range(max_retries + 1):
            raw = self.generate_or_queue(
                task=task,
                prompt=current_prompt,
                model=model,
                response_format=schema,
            )
            try:
                decoded = json.loads(raw)
                return response_model.model_validate(decoded)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                validation_error = str(exc)
                if attempt < max_retries:
                    current_prompt = (
                        f"{prompt}\n\nYour previous response was invalid. Return only JSON matching "
                        f"the requested schema. Validation detail: {validation_error[:800]}"
                    )
        raise InvalidLLMResponse(
            f"Ollama returned invalid JSON for task '{task}' after {max_retries + 1} attempt(s): "
            f"{validation_error}"
        )

    def generate_or_queue(
        self,
        *,
        task: str,
        prompt: str,
        model: str | None = None,
        response_format: str | dict[str, Any] | None = None,
        max_attempts: int = 5,
    ) -> str:
        """Generate now, or persist the exact local generation task for retry.

        The raised error includes the queued task ID so callers can show a clear
        status. ``QueueWorker`` stores a later result on the task row.
        """
        selected_model = self._resolve_model(model)
        try:
            return self.generate(
                task=task,
                prompt=prompt,
                model=selected_model,
                response_format=response_format,
            )
        except OllamaUnavailable as exc:
            payload: dict[str, Any] = {
                "task": task,
                "prompt": prompt,
                "model": selected_model,
            }
            if response_format is not None:
                payload["response_format"] = response_format
            task_id = enqueue_task(
                LLM_GENERATION_TASK,
                payload,
                max_attempts=max_attempts,
                db_path=self.db_path,
            )
            raise OllamaUnavailable(
                f"{exc} The AI task has been queued with ID {task_id}.", task_id=task_id
            ) from exc


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
