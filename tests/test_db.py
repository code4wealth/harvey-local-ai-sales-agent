import sqlite3

from app import db


def test_schema_initializes_all_phase_tables_idempotently(db_path):
    conn = db.connect()
    try:
        db.init_db(conn)
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "products", "business_profiles", "icps", "prospects", "signals",
            "prospect_research", "problem_statements", "scores", "emails", "replies",
            "inference_log", "task_queue", "pipeline_runs", "pipeline_steps",
        } <= names
    finally:
        conn.close()


def test_init_db_migrates_existing_inference_log_status_and_load_seconds(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    try:
        conn.execute(
            "CREATE TABLE inference_log ("
            "id INTEGER PRIMARY KEY, task TEXT NOT NULL, model TEXT NOT NULL, host TEXT NOT NULL, "
            "prompt_tokens INTEGER NOT NULL DEFAULT 0, eval_tokens INTEGER NOT NULL DEFAULT 0, "
            "seconds REAL NOT NULL DEFAULT 0.0, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO inference_log (task, model, host, created_at) VALUES ('old', 'qwen3:4b', 'local', 'now')"
        )
        db.init_db(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(inference_log)")}
        assert "status" in columns
        assert "load_seconds" in columns
        row = conn.execute("SELECT status, load_seconds FROM inference_log").fetchone()
        assert row == ("ok", None)
    finally:
        conn.close()


def test_queue_records_retries_and_keeps_terminal_rows(db_path):
    conn = db.connect()
    try:
        task_id = db.enqueue_task(conn, "unit-test", {"key": "value"}, max_attempts=2)
        db.start_attempt(conn, task_id)
        assert db.finish_attempt(conn, task_id, error="temporary") == "queued"
        db.start_attempt(conn, task_id)
        assert db.finish_attempt(conn, task_id, error="persistent") == "failed"
        row = db.get_task(conn, task_id)
        assert row is not None
        assert row["status"] == "failed"
        assert row["attempts"] == 2
        assert row["last_error"] == "persistent"
        assert db.queue_counts(conn)["failed"] == 1
    finally:
        conn.close()


def test_crash_recovery_requeues_or_fails_stale_tasks(db_path):
    conn = db.connect()
    try:
        retry_id = db.enqueue_task(conn, "unit-test", max_attempts=2)
        exhausted_id = db.enqueue_task(conn, "unit-test", max_attempts=1)
        db.start_attempt(conn, retry_id)
        db.start_attempt(conn, exhausted_id)
        assert db.reset_stale_running(conn) == 2
        assert db.get_task(conn, retry_id)["status"] == "queued"
        exhausted = db.get_task(conn, exhausted_id)
        assert exhausted["status"] == "failed"
        assert "max attempts reached" in exhausted["last_error"]
    finally:
        conn.close()
