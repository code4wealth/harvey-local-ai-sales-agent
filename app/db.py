"""SQLite persistence for products, local inference tasks, and inference logs."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

LOCAL_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_DB_PATH = Path("./data/harvey.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    company_info_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    run_after TEXT NOT NULL,
    last_error TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_task_queue_ready
    ON task_queue(status, run_after, id);

CREATE TABLE IF NOT EXISTS inference_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    model TEXT NOT NULL,
    host TEXT NOT NULL CHECK (host = 'http://127.0.0.1:11434'),
    prompt_tokens INTEGER,
    eval_tokens INTEGER,
    tokens_per_second REAL CHECK (tokens_per_second IS NULL OR tokens_per_second >= 0),
    latency_seconds REAL NOT NULL CHECK (latency_seconds >= 0),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'error')),
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_inference_log_created_at
    ON inference_log(created_at DESC, id DESC);
"""


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve the local SQLite file, honoring the non-secret DB_PATH setting."""
    if db_path is not None:
        return Path(db_path).expanduser()
    return Path(os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    instant = value or _now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def connect_db(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open and close a configured SQLite connection for one operation."""
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db_path: str | Path | None = None) -> Path:
    """Create the foundation schema if it does not already exist."""
    path = resolve_db_path(db_path)
    with connect_db(path) as connection:
        connection.executescript(_SCHEMA)
        inference_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(inference_log)")
        }
        if "tokens_per_second" not in inference_columns:
            connection.execute(
                "ALTER TABLE inference_log ADD COLUMN tokens_per_second REAL"
            )
    return path


def create_product(
    name: str,
    *,
    description: str = "",
    company_info_path: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Create a product and return its database identifier."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Product name must not be blank.")
    init_db(db_path)
    now = _timestamp()
    with connect_db(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO products
               (name, description, company_info_path, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (clean_name, description.strip(), company_info_path, now, now),
        )
        return int(cursor.lastrowid)


def get_product(product_id: int, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with connect_db(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row is not None else None


def list_products(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect_db(db_path) as connection:
        rows = connection.execute("SELECT * FROM products ORDER BY name, id").fetchall()
        return [dict(row) for row in rows]


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    task = dict(row)
    task["payload"] = json.loads(task.pop("payload_json"))
    result_json = task.pop("result_json")
    task["result"] = json.loads(result_json) if result_json is not None else None
    return task


def enqueue_task(
    task_type: str,
    payload: Mapping[str, Any],
    *,
    max_attempts: int = 5,
    delay_seconds: float = 0,
    db_path: str | Path | None = None,
) -> int:
    """Persist a local task for the queue worker."""
    clean_type = task_type.strip()
    if not clean_type:
        raise ValueError("Task type must not be blank.")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one.")
    now = _now()
    run_after = now + timedelta(seconds=max(0.0, delay_seconds))
    payload_json = _dump_json(dict(payload))
    init_db(db_path)
    with connect_db(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO task_queue
               (task_type, payload_json, status, attempts, max_attempts, run_after,
                created_at, updated_at)
               VALUES (?, ?, 'queued', 0, ?, ?, ?, ?)""",
            (clean_type, payload_json, max_attempts, _timestamp(run_after), _timestamp(now), _timestamp(now)),
        )
        return int(cursor.lastrowid)


def claim_next_task(*, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Atomically claim the next ready task, incrementing its attempt count."""
    init_db(db_path)
    now = _timestamp()
    with connect_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT * FROM task_queue
               WHERE status = 'queued' AND run_after <= ?
               ORDER BY run_after, id LIMIT 1""",
            (now,),
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        task_id = int(row["id"])
        connection.execute(
            """UPDATE task_queue
               SET status = 'running', attempts = attempts + 1,
                   updated_at = ?, started_at = ?, last_error = NULL
               WHERE id = ? AND status = 'queued'""",
            (now, now, task_id),
        )
        updated = connection.execute(
            "SELECT * FROM task_queue WHERE id = ?", (task_id,)
        ).fetchone()
        connection.commit()
        return _decode_task(updated)


def retry_task(
    task_id: int,
    error: str,
    *,
    delay_seconds: float = 0,
    db_path: str | Path | None = None,
) -> bool:
    """Requeue a running task, or mark it failed when its retry budget is spent."""
    init_db(db_path)
    now = _now()
    with connect_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT status, attempts, max_attempts FROM task_queue WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None or row["status"] != "running":
            connection.rollback()
            return False
        if int(row["attempts"]) >= int(row["max_attempts"]):
            connection.execute(
                """UPDATE task_queue SET status = 'failed', last_error = ?,
                   updated_at = ?, completed_at = ?, started_at = NULL WHERE id = ?""",
                (error, _timestamp(now), _timestamp(now), task_id),
            )
            connection.commit()
            return False
        run_after = now + timedelta(seconds=max(0.0, delay_seconds))
        connection.execute(
            """UPDATE task_queue SET status = 'queued', last_error = ?,
               run_after = ?, updated_at = ?, started_at = NULL WHERE id = ?""",
            (error, _timestamp(run_after), _timestamp(now), task_id),
        )
        connection.commit()
        return True


def complete_task(
    task_id: int,
    result: Any = None,
    *,
    db_path: str | Path | None = None,
) -> None:
    """Persist a task's result and mark it complete."""
    init_db(db_path)
    now = _timestamp()
    result_json = None if result is None else _dump_json(result)
    with connect_db(db_path) as connection:
        connection.execute(
            """UPDATE task_queue SET status = 'completed', result_json = ?,
               last_error = NULL, updated_at = ?, completed_at = ?, started_at = NULL
               WHERE id = ?""",
            (result_json, now, now, task_id),
        )


def fail_task(
    task_id: int,
    error: str,
    *,
    db_path: str | Path | None = None,
) -> None:
    """Mark a non-retryable task failure."""
    init_db(db_path)
    now = _timestamp()
    with connect_db(db_path) as connection:
        connection.execute(
            """UPDATE task_queue SET status = 'failed', last_error = ?,
               updated_at = ?, completed_at = ?, started_at = NULL WHERE id = ?""",
            (error, now, now, task_id),
        )


def get_task(task_id: int, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with connect_db(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM task_queue WHERE id = ?", (task_id,)
        ).fetchone()
        return _decode_task(row)


def record_inference(
    *,
    task: str,
    model: str,
    prompt_tokens: int | None,
    eval_tokens: int | None,
    latency_seconds: float,
    status: str,
    tokens_per_second: float | None = None,
    error: str | None = None,
    host: str = LOCAL_OLLAMA_HOST,
    db_path: str | Path | None = None,
) -> int:
    """Write one success or failure row for a local inference request."""
    if host != LOCAL_OLLAMA_HOST:
        raise ValueError("Inference logs may only record the fixed local Ollama host.")
    if status not in {"success", "error"}:
        raise ValueError("Inference status must be 'success' or 'error'.")
    if latency_seconds < 0:
        raise ValueError("latency_seconds must be non-negative.")
    if tokens_per_second is not None and tokens_per_second < 0:
        raise ValueError("tokens_per_second must be non-negative.")
    init_db(db_path)
    with connect_db(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO inference_log
               (task, model, host, prompt_tokens, eval_tokens, tokens_per_second,
                latency_seconds, created_at, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task,
                model,
                host,
                prompt_tokens,
                eval_tokens,
                tokens_per_second,
                float(latency_seconds),
                _timestamp(),
                status,
                error,
            ),
        )
        return int(cursor.lastrowid)


def list_inference_logs(
    *, limit: int = 100, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be at least one.")
    init_db(db_path)
    with connect_db(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM inference_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
