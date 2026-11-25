"""SQLite storage for Harvey Local. Stdlib sqlite3 only — no ORM, no server.

Everything (products, AI outputs, inference log, task queue) lives in one
file, by default ./data/harvey.db (override with the DB_PATH environment
variable; that is the only supported override). The schema is created
idempotently by init_db() at app startup and in tests.
"""

from __future__ import annotations

import json
import math
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
    temperature REAL NOT NULL DEFAULT 0.0,
    seed        INTEGER NOT NULL DEFAULT 42,
    repeat_penalty REAL NOT NULL DEFAULT 1.0,
    prompt_hash TEXT NOT NULL DEFAULT '',
    commit_hash TEXT NOT NULL DEFAULT '',
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
    temperature    REAL NOT NULL DEFAULT 0.0,
    seed           INTEGER NOT NULL DEFAULT 42,
    repeat_penalty REAL NOT NULL DEFAULT 1.0,
    prompt_hash    TEXT NOT NULL DEFAULT '',
    commit_hash    TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS signal_runs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id            INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    product_id             INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    status                 TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    model_name             TEXT,
    prompt_hash            TEXT NOT NULL DEFAULT '',
    commit_hash            TEXT NOT NULL DEFAULT '',
    temperature            REAL NOT NULL DEFAULT 0.0,
    seed                   INTEGER NOT NULL DEFAULT 42,
    repeat_penalty         REAL NOT NULL DEFAULT 1.0,
    quote_retries          INTEGER NOT NULL DEFAULT 0 CHECK (quote_retries >= 0),
    signals_json           TEXT,
    drop_counts_json       TEXT,
    removed_content_json   TEXT,
    error                  TEXT,
    queue_task_id          INTEGER,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signal_runs_prospect
  ON signal_runs(prospect_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id   INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    signal_run_id INTEGER REFERENCES signal_runs(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,
    evidence      TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 0.0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_prospect ON signals(prospect_id);

CREATE TABLE IF NOT EXISTS problem_statements (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id             INTEGER REFERENCES products(id) ON DELETE CASCADE,
    prospect_id            INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    business_profile_id    INTEGER REFERENCES business_profiles(id) ON DELETE SET NULL,
    icp_id                 INTEGER REFERENCES icps(id) ON DELETE SET NULL,
    signal_run_id          INTEGER REFERENCES signal_runs(id) ON DELETE SET NULL,
    source_signal_ids_json TEXT NOT NULL DEFAULT '[]',
    status                 TEXT NOT NULL DEFAULT 'running'
                           CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')),
    statement              TEXT NOT NULL DEFAULT '',
    evidence_json          TEXT,
    error                  TEXT,
    model_name             TEXT,
    prompt_hash            TEXT NOT NULL DEFAULT '',
    commit_hash            TEXT NOT NULL DEFAULT '',
    temperature            REAL NOT NULL DEFAULT 0.0,
    seed                   INTEGER NOT NULL DEFAULT 42,
    repeat_penalty         REAL NOT NULL DEFAULT 1.0,
    queue_task_id          INTEGER,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS sample_replies (
    reply_id    TEXT PRIMARY KEY,
    reply_text  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reply_classifications (
    reply_id     TEXT PRIMARY KEY REFERENCES sample_replies(reply_id) ON DELETE CASCADE,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'queued', 'running', 'succeeded', 'failed')),
    label        TEXT,
    confidence   REAL,
    rationale    TEXT,
    model_name   TEXT,
    prompt_hash  TEXT NOT NULL DEFAULT '',
    commit_hash  TEXT NOT NULL DEFAULT '',
    temperature  REAL NOT NULL DEFAULT 0.0,
    seed         INTEGER NOT NULL DEFAULT 42,
    repeat_penalty REAL NOT NULL DEFAULT 1.0,
    error        TEXT,
    queue_task_id INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reply_classifications_status
  ON reply_classifications(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS inference_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task          TEXT NOT NULL,
    model         TEXT NOT NULL,
    host          TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    eval_tokens   INTEGER NOT NULL DEFAULT 0,
    seconds       REAL NOT NULL DEFAULT 0.0,
    load_seconds  REAL,
    temperature   REAL NOT NULL DEFAULT 0.0,
    seed          INTEGER NOT NULL DEFAULT 42,
    repeat_penalty REAL NOT NULL DEFAULT 1.0,
    status        TEXT NOT NULL DEFAULT 'ok'
                  CHECK (status IN ('ok', 'error:unavailable', 'error:timeout', 'error:http', 'error:invalid_json')),
    prompt_hash   TEXT NOT NULL DEFAULT '',
    commit_hash   TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    model_name  TEXT,
    prospect_limit INTEGER,
    prospect_count INTEGER,
    queue_task_id INTEGER,
    started_at  TEXT,
    finished_at TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pipeline_product ON pipeline_runs(product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    step_name   TEXT NOT NULL,
    step_order  INTEGER NOT NULL DEFAULT 0,
    prospect_id INTEGER REFERENCES prospects(id) ON DELETE SET NULL,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    last_error  TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
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
    prompt_hash    TEXT NOT NULL DEFAULT '',
    commit_hash    TEXT NOT NULL DEFAULT '',
    temperature    REAL NOT NULL DEFAULT 0.0,
    seed           INTEGER NOT NULL DEFAULT 42,
    repeat_penalty REAL NOT NULL DEFAULT 1.0,
    result_json    TEXT,
    error          TEXT,
    queue_task_id  INTEGER,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_product
  ON workflow_runs(product_id, workflow, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS draft_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    prospect_id         INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    business_profile_id INTEGER REFERENCES business_profiles(id) ON DELETE SET NULL,
    signal_run_id       INTEGER REFERENCES signal_runs(id) ON DELETE SET NULL,
    status              TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')),
    subject             TEXT,
    body                TEXT,
    evidence_used_json  TEXT,
    error               TEXT,
    model_name          TEXT,
    prompt_hash         TEXT NOT NULL DEFAULT '',
    commit_hash         TEXT NOT NULL DEFAULT '',
    temperature         REAL NOT NULL DEFAULT 0.0,
    seed                INTEGER NOT NULL DEFAULT 42,
    repeat_penalty      REAL NOT NULL DEFAULT 1.0,
    queue_task_id       INTEGER,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_draft_runs_product_prospect
  ON draft_runs(product_id, prospect_id, created_at DESC, id DESC);
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


def merge_duplicate_products(conn: sqlite3.Connection) -> int:
    """Merge products with case-folded duplicate names into their oldest row.

    Every table column named ``product_id`` is re-pointed before duplicate
    product rows are deleted. Queue payloads store product IDs in JSON, so
    those references are updated separately. Prospect IDs stay stable, which
    also preserves their signals, drafts, replies, scores, and research rows.
    """
    product_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(products)")}
    optional_columns = ("description", "docs_path", "created_at", "updated_at")
    select_columns = ["id", "name"] + [
        column if column in product_columns else f"'' AS {column}"
        for column in optional_columns
    ]
    rows = conn.execute(
        f"SELECT {', '.join(select_columns)} FROM products ORDER BY id"
    ).fetchall()
    groups: dict[str, list[sqlite3.Row | tuple]] = {}
    for row in rows:
        key = str(row["name"] if isinstance(row, sqlite3.Row) else row[1]).strip().casefold()
        groups.setdefault(key, []).append(row)
    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    if not duplicate_groups:
        return 0

    remap: dict[int, int] = {}
    conn.execute("SAVEPOINT merge_duplicate_products")
    try:
        for group in duplicate_groups:
            get = (lambda row, key: row[key]) if isinstance(group[0], sqlite3.Row) else (
                lambda row, key: row[{"id": 0, "name": 1, "description": 2, "docs_path": 3,
                                      "created_at": 4, "updated_at": 5}[key]]
            )
            keeper_id = int(get(group[0], "id"))
            canonical_name = str(get(group[0], "name") or "").strip()
            description = next(
                (str(get(row, "description") or "").strip() for row in group
                 if str(get(row, "description") or "").strip()),
                "",
            )
            docs_path = next(
                (str(get(row, "docs_path") or "").strip() for row in group
                 if str(get(row, "docs_path") or "").strip()),
                "",
            )
            updated_at = max(str(get(row, "updated_at") or "") for row in group)
            updates = {"name": canonical_name}
            if "description" in product_columns:
                updates["description"] = description
            if "docs_path" in product_columns:
                updates["docs_path"] = docs_path
            if "updated_at" in product_columns:
                updates["updated_at"] = updated_at
            set_clause = ", ".join(f'"{column}" = ?' for column in updates)
            conn.execute(
                f"UPDATE products SET {set_clause} WHERE id = ?",
                (*updates.values(), keeper_id),
            )
            for duplicate in group[1:]:
                remap[int(get(duplicate, "id"))] = keeper_id

        table_names = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in table_names:
            if table == "products":
                continue
            escaped_table = table.replace('"', '""')
            columns = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{escaped_table}")')}
            if "product_id" in columns:
                for old_id, keeper_id in remap.items():
                    conn.execute(
                        f'UPDATE "{escaped_table}" SET product_id = ? WHERE product_id = ?',
                        (keeper_id, old_id),
                    )

        if "task_queue" in table_names:
            task_rows = conn.execute("SELECT id, payload_json FROM task_queue").fetchall()
            for task in task_rows:
                try:
                    payload = json.loads(task["payload_json"] if isinstance(task, sqlite3.Row) else task[1])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                try:
                    old_id = int(payload.get("product_id"))
                except (TypeError, ValueError):
                    continue
                if old_id not in remap:
                    continue
                payload["product_id"] = remap[old_id]
                task_id = task["id"] if isinstance(task, sqlite3.Row) else task[0]
                conn.execute(
                    "UPDATE task_queue SET payload_json = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(task_id)),
                )

        for duplicate_id in remap:
            conn.execute("DELETE FROM products WHERE id = ?", (duplicate_id,))
        conn.execute("RELEASE SAVEPOINT merge_duplicate_products")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT merge_duplicate_products")
        conn.execute("RELEASE SAVEPOINT merge_duplicate_products")
        raise
    return len(remap)


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    pipeline_run_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)")
    }
    for column, definition in {
        "model_name": "TEXT",
        "prospect_limit": "INTEGER",
        "prospect_count": "INTEGER",
        "queue_task_id": "INTEGER",
    }.items():
        if column not in pipeline_run_columns:
            conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {column} {definition}")
    pipeline_step_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(pipeline_steps)")
    }
    for column, definition in {
        "step_order": "INTEGER NOT NULL DEFAULT 0",
        "prospect_id": "INTEGER REFERENCES prospects(id) ON DELETE SET NULL",
        "result_json": "TEXT NOT NULL DEFAULT '{}'",
    }.items():
        if column not in pipeline_step_columns:
            conn.execute(f"ALTER TABLE pipeline_steps ADD COLUMN {column} {definition}")
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

    signal_columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)")}
    if "signal_run_id" not in signal_columns:
        conn.execute(
            "ALTER TABLE signals ADD COLUMN signal_run_id INTEGER "
            "REFERENCES signal_runs(id) ON DELETE CASCADE"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_signals_run ON signals(signal_run_id, id)"
    )

    problem_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(problem_statements)")
    }
    problem_migrations = {
        "product_id": "INTEGER REFERENCES products(id) ON DELETE CASCADE",
        "business_profile_id": (
            "INTEGER REFERENCES business_profiles(id) ON DELETE SET NULL"
        ),
        "icp_id": "INTEGER REFERENCES icps(id) ON DELETE SET NULL",
        "signal_run_id": "INTEGER REFERENCES signal_runs(id) ON DELETE SET NULL",
        "source_signal_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "status": (
            "TEXT NOT NULL DEFAULT 'succeeded' CHECK "
            "(status IN ('queued', 'running', 'succeeded', 'failed', 'skipped'))"
        ),
        "evidence_json": "TEXT",
        "error": "TEXT",
        "model_name": "TEXT",
        "temperature": "REAL NOT NULL DEFAULT 0.0",
        "seed": "INTEGER NOT NULL DEFAULT 42",
        "repeat_penalty": "REAL NOT NULL DEFAULT 1.0",
        "queue_task_id": "INTEGER",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in problem_migrations.items():
        if column not in problem_columns:
            conn.execute(
                f"ALTER TABLE problem_statements ADD COLUMN {column} {definition}"
            )
    conn.execute(
        "UPDATE problem_statements SET product_id = ("
        "SELECT product_id FROM prospects WHERE prospects.id = problem_statements.prospect_id) "
        "WHERE product_id IS NULL"
    )
    conn.execute(
        "UPDATE problem_statements SET updated_at = created_at "
        "WHERE updated_at IS NULL OR updated_at = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_problem_statements_product_prospect "
        "ON problem_statements(product_id, prospect_id, created_at DESC, id DESC)"
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

    for table in (
        "workflow_runs", "signal_runs", "reply_classifications", "inference_log", "draft_runs"
    ):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "temperature" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN temperature REAL NOT NULL DEFAULT 0.0"
            )
        if "seed" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN seed INTEGER NOT NULL DEFAULT 42")
        if "repeat_penalty" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN repeat_penalty REAL NOT NULL DEFAULT 1.0"
            )

    columns = {row[1] for row in conn.execute("PRAGMA table_info(signal_runs)")}
    if "quote_retries" not in columns:
        conn.execute(
            "ALTER TABLE signal_runs ADD COLUMN quote_retries INTEGER NOT NULL DEFAULT 0 "
            "CHECK (quote_retries >= 0)"
        )

    columns = {row[1] for row in conn.execute("PRAGMA table_info(inference_log)")}
    if "status" not in columns:
        conn.execute(
            "ALTER TABLE inference_log ADD COLUMN status TEXT NOT NULL DEFAULT 'ok' "
            "CHECK (status IN ('ok', 'error:unavailable', 'error:timeout', 'error:http', 'error:invalid_json'))"
        )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(inference_log)")}
    if "load_seconds" not in columns:
        conn.execute("ALTER TABLE inference_log ADD COLUMN load_seconds REAL")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(inference_log)")}
    for column, definition in {
        "prompt_hash": "TEXT NOT NULL DEFAULT ''",
        "commit_hash": "TEXT NOT NULL DEFAULT ''",
    }.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE inference_log ADD COLUMN {column} {definition}")

    output_traceability = {
        "temperature": "REAL NOT NULL DEFAULT 0.0",
        "seed": "INTEGER NOT NULL DEFAULT 42",
        "repeat_penalty": "REAL NOT NULL DEFAULT 1.0",
        "prompt_hash": "TEXT NOT NULL DEFAULT ''",
        "commit_hash": "TEXT NOT NULL DEFAULT ''",
    }
    for table in ("business_profiles", "icps"):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in output_traceability.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    for table in (
        "workflow_runs", "signal_runs", "problem_statements", "draft_runs",
        "reply_classifications",
    ):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column in ("prompt_hash", "commit_hash"):
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )

    merge_duplicate_products(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_name_nocase "
        "ON products(name COLLATE NOCASE)"
    )
    conn.commit()


# ---------------- imported sample replies ----------------

def upsert_sample_replies(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> int:
    """Store reply IDs and text only; labels remain in the offline evaluator."""
    now = utcnow()
    for row in rows:
        reply_id = str(row.get("reply_id", "")).strip()
        reply_text = row.get("text")
        if not reply_id or not isinstance(reply_text, str) or not reply_text.strip():
            raise ValueError("sample reply requires a non-empty reply_id and text")
        conn.execute(
            "INSERT INTO sample_replies (reply_id, reply_text, created_at, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(reply_id) DO UPDATE SET "
            "reply_text = excluded.reply_text, updated_at = excluded.updated_at",
            (reply_id, reply_text, now, now),
        )
    conn.commit()
    return len(rows)


def get_sample_reply(conn: sqlite3.Connection, reply_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT reply_id, reply_text, created_at, updated_at FROM sample_replies WHERE reply_id = ?",
        (str(reply_id).strip(),),
    ).fetchone()


def list_sample_replies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT reply_id, reply_text, created_at, updated_at FROM sample_replies ORDER BY reply_id"
        ).fetchall()
    )


def start_reply_classification(
    conn: sqlite3.Connection,
    *,
    reply_id: str,
    model_name: str,
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
) -> None:
    reply_id = str(reply_id).strip()
    if get_sample_reply(conn, reply_id) is None:
        raise LookupError(f"reply {reply_id} not found; import replies first")
    now = utcnow()
    conn.execute(
        "INSERT INTO reply_classifications "
        "(reply_id, status, model_name, temperature, seed, repeat_penalty, created_at, updated_at) "
        "VALUES (?, 'running', ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(reply_id) DO UPDATE SET status = 'running', label = NULL, "
        "confidence = NULL, rationale = NULL, model_name = excluded.model_name, "
        "temperature = excluded.temperature, seed = excluded.seed, "
        "repeat_penalty = excluded.repeat_penalty, "
        "error = NULL, queue_task_id = NULL, updated_at = excluded.updated_at",
        (
            reply_id,
            str(model_name),
            float(temperature),
            int(seed),
            float(repeat_penalty),
            now,
            now,
        ),
    )
    conn.commit()


def update_reply_classification(
    conn: sqlite3.Connection,
    *,
    reply_id: str,
    status: str,
    model_name: str | None = None,
    label: str | None = None,
    confidence: float | None = None,
    rationale: str | None = None,
    error: str | None = None,
    queue_task_id: int | None = None,
    prompt_hash: str | None = None,
    commit_hash: str | None = None,
) -> None:
    if status not in {"pending", "queued", "running", "succeeded", "failed"}:
        raise ValueError(f"invalid reply classification status: {status!r}")
    if status == "succeeded" and (label is None or confidence is None or rationale is None):
        raise ValueError("a succeeded reply classification requires a validated result")
    cur = conn.execute(
        "UPDATE reply_classifications SET status = ?, model_name = COALESCE(?, model_name), "
        "prompt_hash = COALESCE(?, prompt_hash), commit_hash = COALESCE(?, commit_hash), "
        "label = ?, confidence = ?, rationale = ?, error = ?, queue_task_id = ?, updated_at = ? "
        "WHERE reply_id = ?",
        (
            status,
            model_name,
            prompt_hash,
            commit_hash,
            label,
            float(confidence) if confidence is not None else None,
            rationale,
            error,
            int(queue_task_id) if queue_task_id is not None else None,
            utcnow(),
            str(reply_id).strip(),
        ),
    )
    if cur.rowcount != 1:
        raise LookupError(f"reply classification {reply_id} not found")
    conn.commit()


def get_reply_classification(conn: sqlite3.Connection, reply_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM reply_classifications WHERE reply_id = ?",
        (str(reply_id).strip(),),
    ).fetchone()


def list_reply_classifications(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM reply_classifications ORDER BY reply_id"
        ).fetchall()
    )


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
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
    prompt_hash: str = "",
    commit_hash: str = "",
) -> int:
    if status not in INFERENCE_STATUSES:
        raise ValueError(f"invalid inference status: {status!r}")
    cur = conn.execute(
        "INSERT INTO inference_log "
        "(task, model, host, prompt_tokens, eval_tokens, seconds, load_seconds, "
        "temperature, seed, repeat_penalty, status, prompt_hash, commit_hash, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task,
            model,
            host,
            int(prompt_tokens),
            int(eval_tokens),
            float(seconds),
            float(load_seconds) if load_seconds is not None else None,
            float(temperature),
            int(seed),
            float(repeat_penalty),
            status,
            str(prompt_hash),
            str(commit_hash),
            utcnow(),
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

class ProductAlreadyExists(ValueError):
    """A product already uses this name, ignoring case."""


def create_product(
    conn: sqlite3.Connection, *, name: str, description: str = "", docs_path: str = ""
) -> int:
    name = str(name).strip()
    if not name:
        raise ValueError("product name must not be empty")
    normalized_name = name.casefold()
    if any(
        str(row[0]).strip().casefold() == normalized_name
        for row in conn.execute("SELECT name FROM products")
    ):
        raise ProductAlreadyExists("Product already exists")
    now = utcnow()
    try:
        cur = conn.execute(
            "INSERT INTO products (name, description, docs_path, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, str(description).strip(), str(docs_path).strip(), now, now),
        )
    except sqlite3.IntegrityError as exc:
        if "products.name" in str(exc).casefold():
            raise ProductAlreadyExists("Product already exists") from exc
        raise
    return int(cur.lastrowid)


def get_product(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM products WHERE id = ?", (int(product_id),)).fetchone()


def list_products(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM products ORDER BY id").fetchall())


def update_product(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    name: str,
    description: str = "",
    docs_path: str = "",
) -> sqlite3.Row | None:
    """Update the locally stored product context and return its current row."""
    product_id = int(product_id)
    name = str(name).strip()
    if not name:
        raise ValueError("product name must not be empty")
    if get_product(conn, product_id) is None:
        return None
    normalized_name = name.casefold()
    duplicate = any(
        str(row["name"]).strip().casefold() == normalized_name
        for row in conn.execute("SELECT id, name FROM products WHERE id != ?", (product_id,))
    )
    if duplicate:
        raise ProductAlreadyExists("Product already exists")
    conn.execute(
        "UPDATE products SET name = ?, description = ?, docs_path = ?, updated_at = ? WHERE id = ?",
        (name, str(description).strip(), str(docs_path).strip(), utcnow(), product_id),
    )
    conn.commit()
    return get_product(conn, product_id)


def create_pipeline_run(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    model_name: str | None,
    steps: list[dict[str, Any]],
    prospect_limit: int = 3,
    prospect_count: int | None = None,
) -> int:
    """Persist one product pipeline and its ordered, prospect-scoped steps."""
    if get_product(conn, product_id) is None:
        raise LookupError(f"product {product_id} not found")
    if prospect_count is None:
        prospect_count = len(
            {step.get("prospect_id") for step in steps if step.get("prospect_id") is not None}
        )
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO pipeline_runs "
        "(product_id, status, model_name, prospect_limit, prospect_count, created_at) "
        "VALUES (?, 'queued', ?, ?, ?, ?)",
        (int(product_id), model_name, int(prospect_limit), int(prospect_count), now),
    )
    run_id = int(cur.lastrowid)
    for index, step in enumerate(steps):
        step_name = str(step.get("step_name", "")).strip()
        if not step_name:
            raise ValueError("pipeline step_name must not be empty")
        prospect_id = step.get("prospect_id")
        if prospect_id is not None:
            prospect = get_prospect(conn, int(prospect_id))
            if prospect is None or int(prospect["product_id"]) != int(product_id):
                raise ValueError("pipeline step prospect does not belong to the product")
        conn.execute(
            "INSERT INTO pipeline_steps (run_id, step_name, step_order, prospect_id, status) "
            "VALUES (?, ?, ?, ?, 'queued')",
            (run_id, step_name, int(step.get("step_order", index)), prospect_id),
        )
    conn.commit()
    return run_id


def update_pipeline_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    model_name: str | None = None,
    queue_task_id: int | None = None,
) -> None:
    if status not in {"queued", "running", "done", "failed"}:
        raise ValueError(f"invalid pipeline status: {status!r}")
    now = utcnow()
    cur = conn.execute(
        "UPDATE pipeline_runs SET status = ?, model_name = COALESCE(?, model_name), "
        "queue_task_id = COALESCE(?, queue_task_id), "
        "started_at = CASE WHEN ? = 'running' THEN COALESCE(started_at, ?) ELSE started_at END, "
        "finished_at = CASE WHEN ? IN ('done', 'failed') THEN ? ELSE NULL END "
        "WHERE id = ?",
        (
            status,
            model_name,
            int(queue_task_id) if queue_task_id is not None else None,
            status,
            now,
            status,
            now,
            int(run_id),
        ),
    )
    if cur.rowcount != 1:
        raise ValueError(f"pipeline run {run_id} not found")
    conn.commit()


def update_pipeline_step(
    conn: sqlite3.Connection,
    step_id: int,
    *,
    status: str,
    last_error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    if status not in {"queued", "running", "done", "failed", "skipped"}:
        raise ValueError(f"invalid pipeline step status: {status!r}")
    result_json = (
        json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if result is not None
        else None
    )
    now = utcnow()
    cur = conn.execute(
        "UPDATE pipeline_steps SET status = ?, last_error = ?, "
        "result_json = COALESCE(?, result_json), "
        "started_at = CASE WHEN ? = 'running' THEN COALESCE(started_at, ?) ELSE started_at END, "
        "finished_at = CASE WHEN ? IN ('done', 'failed', 'skipped') THEN ? ELSE NULL END "
        "WHERE id = ?",
        (status, last_error, result_json, status, now, status, now, int(step_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"pipeline step {step_id} not found")
    conn.commit()


def get_pipeline_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (int(run_id),)).fetchone()


def latest_pipeline_run(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM pipeline_runs WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (int(product_id),),
    ).fetchone()


def list_pipeline_steps(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT pipeline_steps.*, prospects.company_name AS prospect_name "
            "FROM pipeline_steps LEFT JOIN prospects ON prospects.id = pipeline_steps.prospect_id "
            "WHERE pipeline_steps.run_id = ? "
            "ORDER BY pipeline_steps.step_order, pipeline_steps.id",
            (int(run_id),),
        ).fetchall()
    )


def get_pipeline_step(conn: sqlite3.Connection, run_id: int, step_name: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM pipeline_steps WHERE run_id = ? AND step_name = ?",
        (int(run_id), str(step_name)),
    ).fetchone()


def create_workflow_run(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    workflow: str,
    model_name: str | None,
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
) -> int:
    if workflow not in {"profile", "icp"}:
        raise ValueError(f"invalid workflow: {workflow!r}")
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO workflow_runs "
        "(product_id, workflow, status, model_name, temperature, seed, repeat_penalty, created_at, updated_at) "
        "VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?)",
        (
            int(product_id),
            workflow,
            model_name,
            float(temperature),
            int(seed),
            float(repeat_penalty),
            now,
            now,
        ),
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
    prompt_hash: str | None = None,
    commit_hash: str | None = None,
) -> None:
    if status not in {"queued", "running", "succeeded", "failed"}:
        raise ValueError(f"invalid workflow run status: {status!r}")
    cur = conn.execute(
        "UPDATE workflow_runs SET status = ?, result_json = NULL, error = ?, "
        "model_name = COALESCE(?, model_name), prompt_hash = COALESCE(?, prompt_hash), "
        "commit_hash = COALESCE(?, commit_hash), queue_task_id = COALESCE(?, queue_task_id), "
        "updated_at = ? WHERE id = ?",
        (status, error, model_name, prompt_hash, commit_hash, queue_task_id, utcnow(), int(run_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"workflow run {run_id} not found")
    conn.commit()


def get_workflow_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (int(run_id),)).fetchone()


def fail_interrupted_workflow_runs(conn: sqlite3.Connection) -> int:
    """Mark workflow runs abandoned by a previous process as terminal failures."""
    cur = conn.execute(
        "UPDATE workflow_runs SET status = 'failed', result_json = NULL, "
        "error = 'interrupted: application restarted before workflow completed', "
        "updated_at = ? WHERE status = 'running'",
        (utcnow(),),
    )
    conn.commit()
    return int(cur.rowcount)


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


def latest_icp(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM icps WHERE product_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
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
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
    prompt_hash: str = "",
    commit_hash: str = "",
) -> None:
    if workflow not in {"profile", "icp"}:
        raise ValueError(f"invalid workflow: {workflow!r}")
    result_json = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    now = utcnow()
    if workflow == "profile":
        conn.execute(
            "INSERT INTO business_profiles "
            "(product_id, profile_json, model_name, temperature, seed, repeat_penalty, "
            "prompt_hash, commit_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(product_id), result_json, model_name, float(temperature), int(seed),
             float(repeat_penalty), prompt_hash, commit_hash, now),
        )
    else:
        conn.execute(
            "INSERT INTO icps "
            "(product_id, icp_json, embedding, embedding_model, model_name, temperature, seed, "
            "repeat_penalty, prompt_hash, commit_hash, created_at) "
            "VALUES (?, ?, NULL, '', ?, ?, ?, ?, ?, ?, ?)",
            (int(product_id), result_json, model_name, float(temperature), int(seed),
             float(repeat_penalty), prompt_hash, commit_hash, now),
        )
    cur = conn.execute(
        "UPDATE workflow_runs SET status = 'succeeded', result_json = ?, error = NULL, "
        "model_name = ?, temperature = ?, seed = ?, repeat_penalty = ?, prompt_hash = ?, "
        "commit_hash = ?, queue_task_id = NULL, updated_at = ? "
        "WHERE id = ? AND product_id = ? AND workflow = ?",
        (result_json, model_name, float(temperature), int(seed), float(repeat_penalty),
         prompt_hash, commit_hash, now, int(run_id), int(product_id), workflow),
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


def create_signal_run(
    conn: sqlite3.Connection,
    *,
    prospect_id: int,
    model_name: str | None,
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
) -> int:
    prospect = get_prospect(conn, prospect_id)
    if prospect is None:
        raise LookupError(f"prospect {prospect_id} not found")
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO signal_runs "
        "(prospect_id, product_id, status, model_name, temperature, seed, repeat_penalty, created_at, updated_at) "
        "VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?)",
        (
            int(prospect_id),
            int(prospect["product_id"]),
            model_name,
            float(temperature),
            int(seed),
            float(repeat_penalty),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_signal_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM signal_runs WHERE id = ?", (int(run_id),)).fetchone()


def latest_signal_run(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM signal_runs WHERE prospect_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(prospect_id),),
    ).fetchone()


def create_problem_statement_run(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    prospect_id: int,
    business_profile_id: int | None,
    icp_id: int | None,
    signal_run_id: int | None,
    source_signal_ids: list[int],
    model_name: str | None,
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
) -> int:
    product = get_product(conn, product_id)
    prospect = get_prospect(conn, prospect_id)
    if product is None:
        raise LookupError(f"product {product_id} not found")
    if prospect is None or int(prospect["product_id"]) != int(product_id):
        raise LookupError(f"prospect {prospect_id} not found for product {product_id}")
    for table, row_id, label in (
        ("business_profiles", business_profile_id, "business profile"),
        ("icps", icp_id, "ICP"),
    ):
        if row_id is None:
            continue
        source = conn.execute(
            f"SELECT product_id FROM {table} WHERE id = ?", (int(row_id),)
        ).fetchone()
        if source is None or int(source["product_id"]) != int(product_id):
            raise ValueError(f"{label} does not belong to the product")
    normalized_signal_ids = sorted({int(signal_id) for signal_id in source_signal_ids})
    if signal_run_id is None and normalized_signal_ids:
        raise ValueError("source signal IDs require a source signal run")
    if signal_run_id is not None:
        signal_run = get_signal_run(conn, signal_run_id)
        if (
            signal_run is None
            or signal_run["status"] != "succeeded"
            or int(signal_run["prospect_id"]) != int(prospect_id)
            or int(signal_run["product_id"]) != int(product_id)
        ):
            raise ValueError("signal run does not belong to the product and prospect")
        if normalized_signal_ids:
            placeholders = ", ".join("?" for _ in normalized_signal_ids)
            matched = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE id IN (" + placeholders + ") "
                "AND prospect_id = ? AND signal_run_id = ?",
                (*normalized_signal_ids, int(prospect_id), int(signal_run_id)),
            ).fetchone()[0]
            if int(matched) != len(normalized_signal_ids):
                raise ValueError("source signal IDs do not belong to the selected signal run")
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO problem_statements "
        "(product_id, prospect_id, business_profile_id, icp_id, signal_run_id, "
        "source_signal_ids_json, status, statement, model_name, temperature, seed, "
        "repeat_penalty, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'running', '', ?, ?, ?, ?, ?, ?)",
        (
            int(product_id),
            int(prospect_id),
            int(business_profile_id) if business_profile_id is not None else None,
            int(icp_id) if icp_id is not None else None,
            int(signal_run_id) if signal_run_id is not None else None,
            json.dumps(normalized_signal_ids, separators=(",", ":")),
            model_name,
            float(temperature),
            int(seed),
            float(repeat_penalty),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_problem_statement_run(
    conn: sqlite3.Connection, run_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM problem_statements WHERE id = ?", (int(run_id),)
    ).fetchone()


def latest_problem_statement_run(
    conn: sqlite3.Connection, *, product_id: int, prospect_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM problem_statements WHERE product_id = ? AND prospect_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (int(product_id), int(prospect_id)),
    ).fetchone()


def update_problem_statement_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    error: str | None = None,
    statement: str | None = None,
    evidence: list[str] | None = None,
    model_name: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    repeat_penalty: float | None = None,
    queue_task_id: int | None = None,
    prompt_hash: str | None = None,
    commit_hash: str | None = None,
) -> None:
    if status not in {"queued", "running", "succeeded", "failed", "skipped"}:
        raise ValueError(f"invalid problem statement status: {status!r}")
    if status == "succeeded" and (
        not isinstance(statement, str) or not statement.strip() or not evidence
    ):
        raise ValueError("a succeeded problem statement requires text and verified evidence")
    if status == "skipped" and not (isinstance(error, str) and error.strip()):
        raise ValueError("a skipped problem statement requires a reason")
    evidence_json = (
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if evidence is not None
        else None
    )
    cur = conn.execute(
        "UPDATE problem_statements SET status = ?, "
        "statement = COALESCE(?, statement), evidence_json = COALESCE(?, evidence_json), "
        "error = ?, model_name = COALESCE(?, model_name), "
        "temperature = COALESCE(?, temperature), seed = COALESCE(?, seed), "
        "repeat_penalty = COALESCE(?, repeat_penalty), "
        "prompt_hash = COALESCE(?, prompt_hash), commit_hash = COALESCE(?, commit_hash), "
        "queue_task_id = COALESCE(?, queue_task_id), updated_at = ? WHERE id = ?",
        (
            status,
            statement,
            evidence_json,
            error,
            model_name,
            float(temperature) if temperature is not None else None,
            int(seed) if seed is not None else None,
            float(repeat_penalty) if repeat_penalty is not None else None,
            prompt_hash,
            commit_hash,
            int(queue_task_id) if queue_task_id is not None else None,
            utcnow(),
            int(run_id),
        ),
    )
    if cur.rowcount != 1:
        raise ValueError(f"problem statement run {run_id} not found")
    conn.commit()


def update_signal_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    error: str | None = None,
    model_name: str | None = None,
    queue_task_id: int | None = None,
    quote_retries: int | None = None,
    prompt_hash: str | None = None,
    commit_hash: str | None = None,
) -> None:
    if status not in {"queued", "running", "succeeded", "failed"}:
        raise ValueError(f"invalid signal run status: {status!r}")
    if quote_retries is not None and int(quote_retries) < 0:
        raise ValueError("quote_retries must be non-negative")
    cur = conn.execute(
        "UPDATE signal_runs SET status = ?, error = ?, "
        "model_name = COALESCE(?, model_name), "
        "prompt_hash = COALESCE(?, prompt_hash), commit_hash = COALESCE(?, commit_hash), "
        "queue_task_id = COALESCE(?, queue_task_id), "
        "quote_retries = COALESCE(?, quote_retries), updated_at = ? WHERE id = ?",
        (
            status,
            error,
            model_name,
            prompt_hash,
            commit_hash,
            queue_task_id,
            int(quote_retries) if quote_retries is not None else None,
            utcnow(),
            int(run_id),
        ),
    )
    if cur.rowcount != 1:
        raise ValueError(f"signal run {run_id} not found")
    conn.commit()


def record_signal_preprocessing(
    conn: sqlite3.Connection, *, run_id: int, removed_content: dict[str, Any]
) -> None:
    removed_json = json.dumps(
        removed_content, ensure_ascii=False, sort_keys=True, allow_nan=False
    )
    cur = conn.execute(
        "UPDATE signal_runs SET removed_content_json = ?, updated_at = ? WHERE id = ?",
        (removed_json, utcnow(), int(run_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"signal run {run_id} not found")
    conn.commit()


def save_signal_run(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    prospect_id: int,
    product_id: int,
    signals: list[dict[str, Any]],
    drop_counts: dict[str, int],
    removed_content: dict[str, Any],
    model_name: str,
    quote_retries: int = 0,
    prompt_hash: str = "",
    commit_hash: str = "",
) -> None:
    result_json = json.dumps(signals, ensure_ascii=False, sort_keys=True, allow_nan=False)
    drop_json = json.dumps(drop_counts, ensure_ascii=False, sort_keys=True, allow_nan=False)
    removed_json = json.dumps(
        removed_content, ensure_ascii=False, sort_keys=True, allow_nan=False
    )
    if int(quote_retries) < 0:
        raise ValueError("quote_retries must be non-negative")
    run = get_signal_run(conn, run_id)
    if (
        run is None
        or int(run["prospect_id"]) != int(prospect_id)
        or int(run["product_id"]) != int(product_id)
    ):
        raise ValueError("signal run does not match the prospect and product")

    now = utcnow()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM signals WHERE signal_run_id = ?", (int(run_id),))
        for signal in signals:
            signal_type = signal.get("type")
            evidence = signal.get("evidence")
            confidence = signal.get("confidence")
            about_company = signal.get("about_company")
            if (
                not isinstance(signal_type, str)
                or not isinstance(evidence, str)
                or about_company is not True
            ):
                raise ValueError("only validated company signals may be persisted")
            if isinstance(confidence, bool):
                raise ValueError("signal confidence must be a finite number from 0 to 1")
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("signal confidence must be a finite number from 0 to 1") from exc
            if not math.isfinite(confidence_value) or not 0.0 <= confidence_value <= 1.0:
                raise ValueError("signal confidence must be a finite number from 0 to 1")
            conn.execute(
                "INSERT INTO signals "
                "(prospect_id, signal_run_id, type, evidence, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (int(prospect_id), int(run_id), signal_type, evidence, confidence_value, now),
            )
        cur = conn.execute(
            "UPDATE signal_runs SET status = 'succeeded', signals_json = ?, "
            "drop_counts_json = ?, removed_content_json = ?, error = NULL, "
            "model_name = ?, prompt_hash = ?, commit_hash = ?, quote_retries = ?, "
            "queue_task_id = NULL, updated_at = ? "
            "WHERE id = ? AND prospect_id = ? AND product_id = ?",
            (
                result_json,
                drop_json,
                removed_json,
                model_name,
                prompt_hash,
                commit_hash,
                int(quote_retries),
                now,
                int(run_id),
                int(prospect_id),
                int(product_id),
            ),
        )
        if cur.rowcount != 1:
            raise ValueError("signal run does not match the prospect and product")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def create_draft_run(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    prospect_id: int,
    business_profile_id: int | None,
    signal_run_id: int | None,
    model_name: str | None,
    temperature: float = 0.0,
    seed: int = 42,
    repeat_penalty: float = 1.0,
) -> int:
    product = get_product(conn, product_id)
    prospect = get_prospect(conn, prospect_id)
    if product is None:
        raise LookupError(f"product {product_id} not found")
    if prospect is None or int(prospect["product_id"]) != int(product_id):
        raise LookupError(f"prospect {prospect_id} not found for product {product_id}")
    if business_profile_id is not None:
        profile_row = conn.execute(
            "SELECT product_id FROM business_profiles WHERE id = ?",
            (int(business_profile_id),),
        ).fetchone()
        if profile_row is None or int(profile_row["product_id"]) != int(product_id):
            raise ValueError("business profile does not belong to the product")
    if signal_run_id is not None:
        signal_run = get_signal_run(conn, signal_run_id)
        if (
            signal_run is None
            or signal_run["status"] != "succeeded"
            or int(signal_run["prospect_id"]) != int(prospect_id)
            or int(signal_run["product_id"]) != int(product_id)
        ):
            raise ValueError("signal run does not belong to the product and prospect")
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO draft_runs "
        "(product_id, prospect_id, business_profile_id, signal_run_id, status, model_name, "
        "temperature, seed, repeat_penalty, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)",
        (
            int(product_id),
            int(prospect_id),
            int(business_profile_id) if business_profile_id is not None else None,
            int(signal_run_id) if signal_run_id is not None else None,
            model_name,
            float(temperature),
            int(seed),
            float(repeat_penalty),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_draft_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM draft_runs WHERE id = ?", (int(run_id),)).fetchone()


def latest_draft_run(
    conn: sqlite3.Connection, *, product_id: int, prospect_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM draft_runs WHERE product_id = ? AND prospect_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (int(product_id), int(prospect_id)),
    ).fetchone()


def update_draft_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    error: str | None = None,
    model_name: str | None = None,
    queue_task_id: int | None = None,
    prompt_hash: str | None = None,
    commit_hash: str | None = None,
) -> None:
    if status not in {"queued", "running", "succeeded", "failed", "skipped"}:
        raise ValueError(f"invalid draft status: {status!r}")
    cur = conn.execute(
        "UPDATE draft_runs SET status = ?, subject = NULL, body = NULL, "
        "evidence_used_json = NULL, error = ?, "
        "model_name = COALESCE(?, model_name), prompt_hash = COALESCE(?, prompt_hash), "
        "commit_hash = COALESCE(?, commit_hash), "
        "queue_task_id = COALESCE(?, queue_task_id), updated_at = ? WHERE id = ?",
        (status, error, model_name, prompt_hash, commit_hash, queue_task_id, utcnow(), int(run_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"draft run {run_id} not found")
    conn.commit()


def save_draft_output(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    subject: str,
    body: str,
    evidence_used: list[str],
    model_name: str,
    prompt_hash: str,
    commit_hash: str,
) -> None:
    if not subject.strip() or not body.strip() or not evidence_used:
        raise ValueError("a successful draft requires subject, body, and verified evidence")
    evidence_json = json.dumps(
        evidence_used, ensure_ascii=False, sort_keys=True, allow_nan=False
    )
    cur = conn.execute(
        "UPDATE draft_runs SET status = 'succeeded', subject = ?, body = ?, "
        "evidence_used_json = ?, error = NULL, model_name = ?, prompt_hash = ?, "
        "commit_hash = ?, queue_task_id = NULL, updated_at = ? WHERE id = ?",
        (subject, body, evidence_json, model_name, prompt_hash, commit_hash, utcnow(), int(run_id)),
    )
    if cur.rowcount != 1:
        raise ValueError(f"draft run {run_id} not found")
    conn.commit()


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


def fail_tasks_for_product(conn: sqlite3.Connection, product_id: int) -> int:
    """Fail queued/running task records whose JSON payload targets a product."""
    changed = 0
    rows = conn.execute(
        "SELECT id, payload_json FROM task_queue WHERE status IN ('queued', 'running')"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            referenced_id = int(payload.get("product_id")) if isinstance(payload, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if referenced_id != int(product_id):
            continue
        cur = conn.execute(
            "UPDATE task_queue SET status = 'failed', last_error = ?, updated_at = ? "
            "WHERE id = ? AND status IN ('queued', 'running')",
            ("Product was deleted before the queued task completed", utcnow(), int(row["id"])),
        )
        changed += int(cur.rowcount)
    return changed


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
