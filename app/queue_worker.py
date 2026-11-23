"""Retry queued local AI tasks when the local inference server is available."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any

from app.db import (
    claim_next_task,
    complete_task,
    fail_task,
    retry_task,
)
from app.llm_client import LLM_GENERATION_TASK, OllamaClient, OllamaUnavailable

TaskHandler = Callable[[Mapping[str, Any]], Any]


class QueueWorker:
    """Small polling worker with bounded exponential retry for Ollama outages."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        llm_client: OllamaClient | None = None,
        handlers: Mapping[str, TaskHandler] | None = None,
        retry_base_seconds: float = 2.0,
        retry_max_seconds: float = 60.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        if retry_base_seconds < 0 or retry_max_seconds < 0 or poll_interval_seconds < 0:
            raise ValueError("Queue timing values must be non-negative.")
        self.db_path = db_path
        self.llm_client = llm_client
        self.handlers: dict[str, TaskHandler] = dict(handlers or {})
        if llm_client is not None:
            self.handlers.setdefault(LLM_GENERATION_TASK, self._run_generation)
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def _run_generation(self, payload: Mapping[str, Any]) -> str:
        if self.llm_client is None:
            raise RuntimeError("No local inference client is configured for queued generation.")
        return self.llm_client.generate(
            task=str(payload["task"]),
            prompt=str(payload["prompt"]),
            model=str(payload["model"]),
            response_format=payload.get("response_format"),
        )

    def run_once(self) -> bool:
        """Process one ready task; return false when the queue has no ready work."""
        task = claim_next_task(db_path=self.db_path)
        if task is None:
            return False
        handler = self.handlers.get(task["task_type"])
        if handler is None:
            fail_task(
                task["id"],
                f"No handler registered for task type '{task['task_type']}'.",
                db_path=self.db_path,
            )
            return True
        try:
            result = handler(task["payload"])
        except OllamaUnavailable as exc:
            retry_delay = min(
                self.retry_base_seconds * (2 ** max(0, task["attempts"] - 1)),
                self.retry_max_seconds,
            )
            retry_task(
                task["id"],
                str(exc),
                delay_seconds=retry_delay,
                db_path=self.db_path,
            )
        except Exception as exc:
            fail_task(task["id"], f"{type(exc).__name__}: {exc}", db_path=self.db_path)
        else:
            complete_task(task["id"], result, db_path=self.db_path)
        return True

    def run_forever(self, stop_event: threading.Event) -> None:
        """Poll until ``stop_event`` is set; waits interruptibly when idle."""
        while not stop_event.is_set():
            if not self.run_once():
                stop_event.wait(self.poll_interval_seconds)
