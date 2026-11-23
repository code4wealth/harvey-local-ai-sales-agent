"""Background retry worker for tasks queued while Ollama was down.

Started from the FastAPI lifespan (app/main.py) as a daemon thread. Each poll
it first checks ollama_up(); only then does it claim due tasks (attempts <
max_attempts), runs the registered handler, and records the outcome in
task_queue. Tasks are never deleted: done / failed rows stay in the table.
Handlers are registered by task_type, e.g. by the workflow modules.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Callable

from app import db
from app.llm_client import OllamaUnavailable, ollama_up

logger = logging.getLogger("harvey.queue")

TaskHandler = Callable[[dict], None]
HANDLERS: dict[str, TaskHandler] = {}


def register_handler(task_type: str, handler: TaskHandler) -> None:
    HANDLERS[task_type] = handler


class QueueWorker:
    def __init__(self, *, poll_seconds: float = 5.0, batch_size: int = 5):
        self.poll_seconds = poll_seconds
        self.batch_size = batch_size
        self._stop = threading.Event()
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

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                attempted = self.run_once()
            except Exception:
                logger.exception("queue worker iteration failed")
                attempted = 0
            # If nothing was runnable (Ollama down or queue empty), wait the
            # full poll interval; otherwise drain the backlog briskly.
            self._stop.wait(self.poll_seconds if attempted == 0 else 0.2)

    def run_once(self) -> int:
        """One poll iteration. Returns how many tasks were attempted."""
        if not ollama_up():
            return 0
        conn = db.connect()
        try:
            tasks = db.fetch_queued_tasks(conn, limit=self.batch_size)
            for task in tasks:
                self._process(conn, task)
            return len(tasks)
        finally:
            conn.close()

    def _process(self, conn, task) -> None:
        db.start_attempt(conn, task["id"])
        try:
            payload = json.loads(task["payload_json"] or "{}")
        except json.JSONDecodeError as exc:
            db.finish_attempt(conn, task["id"], error=f"payload_json is not valid JSON: {exc}")
            return
        handler = HANDLERS.get(task["task_type"])
        try:
            if handler is None:
                raise RuntimeError(f"no handler registered for task_type {task['task_type']!r}")
            handler(payload)
        except OllamaUnavailable as exc:
            db.finish_attempt(conn, task["id"], error=f"OllamaUnavailable: {exc}")
        except Exception as exc:
            logger.exception("queued task %s failed", task["id"])
            db.finish_attempt(conn, task["id"], error=f"{type(exc).__name__}: {exc}")
        else:
            db.finish_attempt(conn, task["id"], error=None)
