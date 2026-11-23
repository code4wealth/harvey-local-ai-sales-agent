"""SQLite storage for Harvey Local. Stdlib sqlite3 only — no ORM, no server.

Everything (products, AI outputs, inference log, task queue) lives in one
file, by default ./data/harvey.db (override with the DB_PATH environment
variable; that is the only supported override). The schema is created
idempotently by init_db() at app startup and in tests.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "./data/harvey.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    docs_path   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    profile_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_product ON business_profiles(product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS icps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    icp_json       TEXT NOT NULL,
    embedding      BLOB,
    embedding_model TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_icps_product ON icps(product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS prospects (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    contact_name   TEXT NOT NULL DEFAULT '',
    contact_title  TEXT NOT NULL DEFAULT '',
    company_name   TEXT NOT NULL DEFAULT '',
    company_domain TEXT NOT NULL DEFAULT '',
    contact_email  TEXT NOT NULL DEFAULT '',
    page_text_path TEXT NOT NULL DEFAULT '',
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prospects_product ON prospects(product_id);

CREATE TABLE IF NOT EXISTS prospect_research (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id     INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    summary         TEXT NOT NULL,
    embedding       BLOB,
    embedding_model TEXT NOT NULL DEFAULT '',
    icp_similarity  REAL,
    source_path     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_prospect ON prospect_research(prospect_id, created_at DESC);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    evidence    TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_prospect ON signals(prospect_id);

CREATE TABLE IF NOT EXISTS problem_statements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    statement   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_problems_prospect ON problem_statements(prospect_id, created_at DESC);

CREATE TABLE IF NOT EXISTS scores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id   INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    score         REAL NOT NULL,
    breakdown_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scores_prospect ON scores(prospect_id, created_at DESC);

CREATE TABLE IF NOT EXISTS emails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    word_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emails_prospect ON emails(prospect_id, created_at DESC);

CREATE TABLE IF NOT EXISTS replies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER REFERENCES prospects(id) ON DELETE SET NULL,
    reply_text  TEXT NOT NULL,
    label       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.0,
    next_action TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inference_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task          TEXT NOT NULL,
    model         TEXT NOT NULL,
    host          TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    eval_tokens   INTEGER NOT NULL DEFAULT 0,
    seconds       REAL NOT NULL DEFAULT 0.0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    started_at  TEXT,
    finished_at TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pipeline_product ON pipeline_runs(product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    step_name   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    last_error  TEXT,
    started_at  TEXT,
    finished_at TEXT,
    UNIQUE (run_id, step_name)
);
CREATE INDEX IF NOT EXISTS idx_pipeline_steps_run ON pipeline_steps(run_id, id);

CREATE TABLE IF NOT EXISTS task_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type     TEXT NOT NULL,
    payload_json  TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 3,
    last_error    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_status ON task_queue(status, created_at);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_db_path() -> str:
    return os.environ.get("DB_PATH", DEFAULT_DB_PATH)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = Path(db_path or get_db_path())
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---------------- inference log ----------------

def log_inference(
    conn: sqlite3.Connection,
    *,
    task: str,
    model: str,
    host: str,
    prompt_tokens: int = 0,
    eval_tokens: int = 0,
    seconds: float = 0.0,
) -> int:
    cur = conn.execute(
        "INSERT INTO inference_log (task, model, host, prompt_tokens, eval_tokens, seconds, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task, model, host, int(prompt_tokens), int(eval_tokens), float(seconds), utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


def latest_inference(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM inference_log ORDER BY id DESC LIMIT 1"
    ).fetchone()


# ---------------- task queue ----------------

def enqueue_task(
    conn: sqlite3.Connection, task_type: str, payload: dict[str, Any] | None = None,
    *, max_attempts: int = 3,
) -> int:
    import json

    now = utcnow()
    cur = conn.execute(
        "INSERT INTO task_queue (task_type, payload_json, status, attempts, max_attempts, created_at, updated_at)"
        " VALUES (?, ?, 'queued', 0, ?, ?, ?)",
        (task_type, json.dumps(payload or {}), int(max_attempts), now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def fetch_queued_tasks(conn: sqlite3.Connection, *, limit: int = 5) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM task_queue WHERE status = 'queued' AND attempts < max_attempts"
            " ORDER BY created_at LIMIT ?",
            (int(limit),),
        ).fetchall()
    )


def get_task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()


def start_attempt(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute(
        "UPDATE task_queue SET attempts = attempts + 1, status = 'running', updated_at = ? WHERE id = ?",
        (utcnow(), task_id),
    )
    conn.commit()


def finish_attempt(conn: sqlite3.Connection, task_id: int, *, error: str | None) -> str:
    """Mark a running attempt done/queued/failed. Tasks are never deleted."""
    row = get_task(conn, task_id)
    if row is None:
        raise ValueError(f"task {task_id} not found")
    if error is None:
        status = "done"
    elif row["attempts"] >= row["max_attempts"]:
        status = "failed"
    else:
        status = "queued"
    conn.execute(
        "UPDATE task_queue SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
        (status, error, utcnow(), task_id),
    )
    conn.commit()
    return status


def reset_stale_running(conn: sqlite3.Connection) -> int:
    """Recover tasks left running by a crash without stranding exhausted tasks."""
    now = utcnow()
    cur = conn.execute(
        """
        UPDATE task_queue SET
          status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
          last_error = CASE WHEN attempts >= max_attempts
            THEN COALESCE(last_error, 'worker stopped before task completed; max attempts reached')
            ELSE COALESCE(last_error, 'worker stopped before task completed') END,
          updated_at = ? WHERE status = 'running'
        """,
        (now,),
    )
    conn.commit()
    return int(cur.rowcount)


def queue_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM task_queue GROUP BY status"
    ).fetchall()
    counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    counts.update({row["status"]: row["n"] for row in rows})
    return counts
