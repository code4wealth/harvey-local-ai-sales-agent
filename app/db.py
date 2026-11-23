"""SQLite storage for Harvey Local. Stdlib sqlite3 only — no ORM, no server.

Everything (products, AI outputs, inference log, task queue) lives in one
file, by default ./data/harvey.db (override with the DB_PATH environment
variable; that is the only supported override). The schema is created
idempotently by init_db() at app startup and in tests.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "./data/harvey.db"
INFERENCE_STATUSES = (
    "ok",
    "error:unavailable",
    "error:timeout",
    "error:http",
    "error:invalid_json",
)

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
    model_name  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_product ON business_profiles(product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS icps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    icp_json       TEXT NOT NULL,
    embedding      BLOB,
    embedding_model TEXT NOT NULL DEFAULT '',
    model_name     TEXT NOT NULL DEFAULT '',
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
    employee_count INTEGER,
    contact_email  TEXT NOT NULL DEFAULT '',
    page_text_path TEXT NOT NULL DEFAULT '',
    page_embedding BLOB,
    page_embedding_model TEXT NOT NULL DEFAULT '',
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
    score         REAL,
    breakdown_json TEXT NOT NULL DEFAULT '{}',
    partial       INTEGER NOT NULL DEFAULT 0,
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
    load_seconds  REAL,
    status        TEXT NOT NULL DEFAULT 'ok'
                  CHECK (status IN ('ok', 'error:unavailable', 'error:timeout', 'error:http', 'error:invalid_json')),
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

CREATE TABLE IF NOT EXISTS workflow_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    workflow       TEXT NOT NULL CHECK (workflow IN ('profile', 'icp')),
    status         TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    model_name     TEXT,
    result_json    TEXT,
    error          TEXT,
    queue_task_id  INTEGER,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_product
  ON workflow_runs(product_id, workflow, created_at DESC, id DESC);
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
    for table in ("business_profiles", "icps"):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "model_name" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN model_name TEXT NOT NULL DEFAULT ''"
            )
    prospect_columns = {row[1] for row in conn.execute("PRAGMA table_info(prospects)")}
    if "employee_count" not in prospect_columns:
        conn.execute("ALTER TABLE prospects ADD COLUMN employee_count INTEGER")
    if "page_embedding" not in prospect_columns:
        conn.execute("ALTER TABLE prospects ADD COLUMN page_embedding BLOB")
    if "page_embedding_model" not in prospect_columns:
        conn.execute(
            "ALTER TABLE prospects ADD COLUMN page_embedding_model TEXT NOT NULL DEFAULT ''"
        )

    score_columns = list(conn.execute("PRAGMA table_info(scores)"))
    score_names = {row[1] for row in score_columns}
    score_is_not_null = any(row[1] == "score" and row[3] for row in score_columns)
    if "partial" not in score_names or score_is_not_null:
        conn.execute("DROP TABLE IF EXISTS scores_migration")
        conn.execute(
            "CREATE TABLE scores_migration ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE, "
            "score REAL, breakdown_json TEXT NOT NULL DEFAULT '{}', "
            "partial INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
        )
        if "partial" in score_names:
            conn.execute(
                "INSERT INTO scores_migration (id, prospect_id, score, breakdown_json, partial, created_at) "
                "SELECT id, prospect_id, score, breakdown_json, partial, created_at FROM scores"
            )
        else:
            conn.execute(
                "INSERT INTO scores_migration (id, prospect_id, score, breakdown_json, partial, created_at) "
                "SELECT id, prospect_id, score, breakdown_json, 0, created_at FROM scores"
            )
        conn.execute("DROP TABLE scores")
        conn.execute("ALTER TABLE scores_migration RENAME TO scores")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_prospect ON scores(prospect_id, created_at DESC)")

    columns = {row[1] for row in conn.execute("PRAGMA table_info(inference_log)")}
    if "status" not in columns:
        conn.execute(
            "ALTER TABLE inference_log ADD COLUMN status TEXT NOT NULL DEFAULT 'ok' "
            "CHECK (status IN ('ok', 'error:unavailable', 'error:timeout', 'error:http', 'error:invalid_json'))"
        )
    if "load_seconds" not in columns:
        conn.execute("ALTER TABLE inference_log ADD COLUMN load_seconds REAL")
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
    load_seconds: float | None = None,
    status: str = "ok",
) -> int:
    if status not in INFERENCE_STATUSES:
        raise ValueError(f"invalid inference status: {status!r}")
    cur = conn.execute(
        "INSERT INTO inference_log "
        "(task, model, host, prompt_tokens, eval_tokens, seconds, load_seconds, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task, model, host, int(prompt_tokens), int(eval_tokens), float(seconds),
            float(load_seconds) if load_seconds is not None else None, status, utcnow(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_inference_status(conn: sqlite3.Connection, log_id: int, status: str) -> None:
    if status not in INFERENCE_STATUSES:
        raise ValueError(f"invalid inference status: {status!r}")
    conn.execute("UPDATE inference_log SET status = ? WHERE id = ?", (status, int(log_id)))
    conn.commit()


def latest_inference(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM inference_log ORDER BY id DESC LIMIT 1"
    ).fetchone()


# ---------------- products, prospects, and deterministic scores ----------------

def create_product(
    conn: sqlite3.Connection, *, name: str, description: str = "", docs_path: str = ""
) -> int:
    name = str(name).strip()
    if not name:
        raise ValueError("product name must not be empty")
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO products (name, description, docs_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, str(description).strip(), str(docs_path).strip(), now, now),
    )
    return int(cur.lastrowid)


def get_product(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM products WHERE id = ?", (int(product_id),)).fetchone()


def list_products(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM products ORDER BY id").fetchall())


def create_workflow_run(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    workflow: str,
    model_name: str | None,
) -> int:
    if workflow not in {"profile", "icp"}:
        raise ValueError(f"invalid workflow: {workflow!r}")
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO workflow_runs "
        "(product_id, workflow, status, model_name, created_at, updated_at) "
        "VALUES (?, ?, 'running', ?, ?, ?)",
        (int(product_id), workflow, model_name, now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_workflow_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    error: str | None = None,
    model_name: str | None = None,
    queue_task_id: int | None = None,
) -> None:
    if status not in {"queued", "running", "succeeded", "failed"}:
        raise ValueError(f"invalid workflow run status: {status!r}")
    cur = conn.execute(
        "UPDATE workflow_runs SET status = ?, result_json = NULL, error = ?, "
        "model_name = COALESCE(?, model_name), queue_task_id = COALESCE(?, queue_task_id), "
        "updated_at = ? WHERE id = ?",
        (status, error, model_name, queue_task_id, utcnow(), int(run_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"workflow run {run_id} not found")
    conn.commit()


def get_workflow_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (int(run_id),)).fetchone()


def latest_workflow_run(
    conn: sqlite3.Connection, *, product_id: int, workflow: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM workflow_runs WHERE product_id = ? AND workflow = ? "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(product_id), workflow),
    ).fetchone()


def latest_business_profile(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM business_profiles WHERE product_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(product_id),),
    ).fetchone()


def save_workflow_output(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    product_id: int,
    workflow: str,
    result: dict[str, Any],
    model_name: str,
) -> None:
    if workflow not in {"profile", "icp"}:
        raise ValueError(f"invalid workflow: {workflow!r}")
    result_json = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    now = utcnow()
    if workflow == "profile":
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (int(product_id), result_json, model_name, now),
        )
    else:
        conn.execute(
            "INSERT INTO icps (product_id, icp_json, embedding, embedding_model, model_name, created_at) "
            "VALUES (?, ?, NULL, '', ?, ?)",
            (int(product_id), result_json, model_name, now),
        )
    cur = conn.execute(
        "UPDATE workflow_runs SET status = 'succeeded', result_json = ?, error = NULL, "
        "model_name = ?, queue_task_id = NULL, updated_at = ? "
        "WHERE id = ? AND product_id = ? AND workflow = ?",
        (result_json, model_name, now, int(run_id), int(product_id), workflow),
    )
    if cur.rowcount != 1:
        raise ValueError(f"workflow run {run_id} does not match product/workflow")
    conn.commit()


def create_prospect(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    contact_name: str = "",
    contact_title: str = "",
    company_name: str = "",
    company_domain: str = "",
    employee_count: int | None = None,
    contact_email: str = "",
    page_text_path: str = "",
    do_not_contact: bool = False,
) -> int:
    if employee_count is not None and (
        isinstance(employee_count, bool) or not isinstance(employee_count, int) or employee_count < 0
    ):
        raise ValueError("employee_count must be a non-negative integer or None")
    if not isinstance(do_not_contact, bool):
        raise ValueError("do_not_contact must be a boolean")
    cur = conn.execute(
        "INSERT INTO prospects (product_id, contact_name, contact_title, company_name, "
        "company_domain, employee_count, contact_email, page_text_path, do_not_contact, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(product_id), str(contact_name).strip(), str(contact_title).strip(),
            str(company_name).strip(), str(company_domain).strip(),
            int(employee_count) if employee_count is not None else None,
            str(contact_email).strip(), str(page_text_path).strip(),
            int(bool(do_not_contact)), utcnow(),
        ),
    )
    return int(cur.lastrowid)


def get_prospect(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM prospects WHERE id = ?", (int(prospect_id),)).fetchone()


def list_prospects(conn: sqlite3.Connection, product_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM prospects WHERE product_id = ? ORDER BY id", (int(product_id),)
        ).fetchall()
    )


def update_prospect_page_path(
    conn: sqlite3.Connection, prospect_id: int, page_text_path: str
) -> None:
    cur = conn.execute(
        "UPDATE prospects SET page_text_path = ?, page_embedding = NULL, "
        "page_embedding_model = '' WHERE id = ?",
        (str(page_text_path), int(prospect_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"prospect {prospect_id} not found")


def save_score(
    conn: sqlite3.Connection,
    *,
    prospect_id: int,
    score: float | None,
    breakdown: dict[str, Any],
    partial: bool,
) -> int:
    import json

    cur = conn.execute(
        "INSERT INTO scores (prospect_id, score, breakdown_json, partial, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            int(prospect_id),
            float(score) if score is not None else None,
            json.dumps(breakdown, ensure_ascii=False, sort_keys=True, allow_nan=False),
            int(bool(partial)),
            utcnow(),
        ),
    )
    return int(cur.lastrowid)


def latest_score(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM scores WHERE prospect_id = ? ORDER BY id DESC LIMIT 1",
        (int(prospect_id),),
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


def fetch_queued_tasks(
    conn: sqlite3.Connection,
    *,
    limit: int = 5,
    task_types: list[str] | None = None,
    exclude_task_types: list[str] | None = None,
) -> list[sqlite3.Row]:
    clauses = ["status = 'queued'", "attempts < max_attempts"]
    params: list[Any] = []
    if task_types is not None:
        if not task_types:
            return []
        placeholders = ", ".join("?" for _ in task_types)
        clauses.append(f"task_type IN ({placeholders})")
        params.extend(task_types)
    if exclude_task_types:
        placeholders = ", ".join("?" for _ in exclude_task_types)
        clauses.append(f"task_type NOT IN ({placeholders})")
        params.extend(exclude_task_types)
    params.append(int(limit))
    query = (
        "SELECT * FROM task_queue WHERE " + " AND ".join(clauses)
        + " ORDER BY created_at, id LIMIT ?"
    )
    return list(conn.execute(query, params).fetchall())


def get_task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()


def start_attempt(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute(
        "UPDATE task_queue SET attempts = attempts + 1, status = 'running', updated_at = ? WHERE id = ?",
        (utcnow(), task_id),
    )
    conn.commit()


def requeue_unavailable_attempt(
    conn: sqlite3.Connection, task_id: int, *, error: str
) -> None:
    """Requeue a handler that found Ollama unavailable without consuming a try."""
    row = get_task(conn, task_id)
    if row is None:
        raise ValueError(f"task {task_id} not found")
    attempts = max(0, int(row["attempts"]) - 1)
    conn.execute(
        "UPDATE task_queue SET status = 'queued', attempts = ?, last_error = ?, updated_at = ? "
        "WHERE id = ?",
        (attempts, str(error), utcnow(), int(task_id)),
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


def fail_task(conn: sqlite3.Connection, task_id: int, error: str) -> None:
    """Mark a non-runnable task terminally failed with a visible error."""
    cur = conn.execute(
        "UPDATE task_queue SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
        (str(error), utcnow(), int(task_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"task {task_id} not found")
    conn.commit()


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
