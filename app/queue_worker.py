"""Background retry worker for tasks queued while Ollama was down.

Started from the FastAPI lifespan (app/main.py) as a daemon thread. Each poll
runs registered deterministic handlers without an Ollama probe, even if older
LLM tasks are waiting. It probes Ollama only when the batch contains handlers
that require it, then records outcomes in task_queue. Tasks are never deleted:
done / failed rows stay in the table. Handlers are registered by task_type.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Callable

from app import db
from app.llm_client import OllamaResponseError, OllamaTimeout, OllamaUnavailable, ollama_up

logger = logging.getLogger("harvey.queue")

TaskHandler = Callable[[dict], None]


@dataclass(frozen=True)
class HandlerRegistration:
    handler: TaskHandler
    requires_ollama: bool = True


HANDLERS: dict[str, HandlerRegistration] = {}


def register_handler(
    task_type: str, handler: TaskHandler, *, requires_ollama: bool = True
) -> None:
    HANDLERS[task_type] = HandlerRegistration(handler, requires_ollama=requires_ollama)


class QueueWorker:
    def __init__(self, *, poll_seconds: float = 5.0, batch_size: int = 5):
        self.poll_seconds = poll_seconds
        self.batch_size = batch_size
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        conn = db.connect()
        try:
            stale = db.reset_stale_running(conn)
            if stale:
                logger.info("reset %d stale running task(s) back to queued", stale)
        finally:
            conn.close()
        self._thread = threading.Thread(target=self._loop, name="queue-worker", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        """Request an immediate queue poll without running handlers in the API thread."""
        self._wake.set()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                attempted = self.run_once()
            except Exception:
                logger.exception("queue worker iteration failed")
                attempted = 0
            # If nothing was runnable (Ollama down or queue empty), wait the
            # full poll interval unless explicitly woken; otherwise drain briskly.
            self._wake.wait(self.poll_seconds if attempted == 0 else 0.2)

    def run_once(self) -> int:
        """One poll iteration. Returns how many runnable tasks were attempted."""
        conn = db.connect()
        try:
            known_types = list(HANDLERS)
            local_types = [
                task_type
                for task_type, registration in HANDLERS.items()
                if not registration.requires_ollama
            ]
            ollama_types = [
                task_type
                for task_type, registration in HANDLERS.items()
                if registration.requires_ollama
            ]
            local_tasks = db.fetch_queued_tasks(
                conn, limit=self.batch_size, task_types=local_types
            )
            remaining = max(0, self.batch_size - len(local_tasks))
            unknown_tasks = (
                db.fetch_queued_tasks(
                    conn, limit=remaining, exclude_task_types=known_types
                )
                if remaining
                else []
            )
            remaining = max(0, remaining - len(unknown_tasks))
            ollama_tasks = (
                db.fetch_queued_tasks(
                    conn, limit=remaining, task_types=ollama_types
                )
                if remaining
                else []
            )
            if not local_tasks and not unknown_tasks and not ollama_tasks:
                return 0

            ollama_available = False
            if ollama_tasks:
                try:
                    ollama_available = ollama_up()
                except (OllamaUnavailable, OllamaTimeout, OllamaResponseError):
                    # Deterministic/local tasks remain runnable even when the
                    # Ollama health probe is down or slow.
                    ollama_available = False

            attempted = 0
            for task in local_tasks + unknown_tasks:
                self._process(conn, task)
                attempted += 1
            if ollama_available:
                for task in ollama_tasks:
                    self._process(conn, task)
                    attempted += 1
            return attempted
        finally:
            conn.close()

    def _process(self, conn, task) -> None:
        registration = HANDLERS.get(task["task_type"])
        db.start_attempt(conn, task["id"])
        if registration is None:
            error = f"no handler registered for task_type {task['task_type']!r}"
            logger.error("queued task %s failed: %s", task["id"], error)
            db.fail_task(conn, task["id"], error)
            return
        try:
            payload = json.loads(task["payload_json"] or "{}")
        except json.JSONDecodeError as exc:
            db.finish_attempt(conn, task["id"], error=f"payload_json is not valid JSON: {exc}")
            return
        try:
            registration.handler(payload)
        except OllamaUnavailable as exc:
            db.requeue_unavailable_attempt(
                conn, task["id"], error=f"{type(exc).__name__}: {exc}"
            )
        except OllamaTimeout as exc:
            db.finish_attempt(conn, task["id"], error=f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            logger.exception("queued task %s failed", task["id"])
            db.finish_attempt(conn, task["id"], error=f"{type(exc).__name__}: {exc}")
        else:
            db.finish_attempt(conn, task["id"], error=None)
