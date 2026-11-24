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
            "inference_log", "task_queue", "pipeline_runs", "pipeline_steps", "workflow_runs",
            "signal_runs", "sample_replies", "reply_classifications", "draft_runs",
        } <= names
        assert "model_name" in {
            row[1] for row in conn.execute("PRAGMA table_info(business_profiles)")
        }
        assert "model_name" in {
            row[1] for row in conn.execute("PRAGMA table_info(icps)")
        }
        assert "signal_run_id" in {
            row[1] for row in conn.execute("PRAGMA table_info(signals)")
        }
        for table in (
            "workflow_runs", "signal_runs", "reply_classifications", "inference_log", "draft_runs"
        ):
            assert {"temperature", "seed", "repeat_penalty"} <= {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
        assert "quote_retries" in {
            row[1] for row in conn.execute("PRAGMA table_info(signal_runs)")
        }
    finally:
        conn.close()


def test_init_db_migrates_signal_run_link_on_existing_signals_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-signals.db")
    try:
        conn.executescript(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
            "CREATE TABLE prospects (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, created_at TEXT NOT NULL);"
            "CREATE TABLE signals (id INTEGER PRIMARY KEY, prospect_id INTEGER NOT NULL, "
            "type TEXT NOT NULL, evidence TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.0, "
            "created_at TEXT NOT NULL);"
            "INSERT INTO signals VALUES (1, 1, 'hiring', 'legacy quote', 0.0, 'old');"
        )
        db.init_db(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)")}
        assert "signal_run_id" in columns
        assert conn.execute("SELECT signal_run_id FROM signals WHERE id = 1").fetchone()[0] is None
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
        assert {"temperature", "seed"} <= columns
        row = conn.execute(
            "SELECT status, load_seconds, temperature, seed FROM inference_log"
        ).fetchone()
        assert row == ("ok", None, 0.0, 42)
    finally:
        conn.close()


def test_init_db_adds_model_names_to_legacy_profile_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-workflows.db")
    try:
        conn.executescript(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "description TEXT NOT NULL DEFAULT '', docs_path TEXT NOT NULL DEFAULT '', "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
            "CREATE TABLE business_profiles (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, "
            "profile_json TEXT NOT NULL, created_at TEXT NOT NULL);"
            "CREATE TABLE icps (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, "
            "icp_json TEXT NOT NULL, embedding BLOB, embedding_model TEXT NOT NULL DEFAULT '', "
            "created_at TEXT NOT NULL);"
            "INSERT INTO business_profiles VALUES (1, 1, '{}', 'old');"
            "INSERT INTO icps VALUES (1, 1, '{}', NULL, '', 'old');"
        )
        db.init_db(conn)
        for table in ("business_profiles", "icps"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "model_name" in columns
            assert conn.execute(f"SELECT model_name FROM {table} WHERE id = 1").fetchone()[0] == ""
    finally:
        conn.close()


def test_init_db_migrates_legacy_prospect_size_and_partial_score_columns(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-batch.db")
    try:
        conn.executescript(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "description TEXT NOT NULL DEFAULT '', docs_path TEXT NOT NULL DEFAULT '', "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
            "CREATE TABLE prospects (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, "
            "contact_name TEXT NOT NULL DEFAULT '', contact_title TEXT NOT NULL DEFAULT '', "
            "company_name TEXT NOT NULL DEFAULT '', company_domain TEXT NOT NULL DEFAULT '', "
            "contact_email TEXT NOT NULL DEFAULT '', page_text_path TEXT NOT NULL DEFAULT '', "
            "do_not_contact INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);"
            "CREATE TABLE scores (id INTEGER PRIMARY KEY, prospect_id INTEGER NOT NULL, "
            "score REAL NOT NULL, breakdown_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);"
            "INSERT INTO products VALUES (1, 'Product', '', '', 'now', 'now');"
            "INSERT INTO prospects VALUES (1, 1, 'Sam', 'VP Sales', 'Acme', '', '', '', 0, 'now');"
            "INSERT INTO scores VALUES (1, 1, 72.5, '{\"title_fit\": 100}', 'now');"
        )
        db.init_db(conn)
        prospect_columns = {row[1] for row in conn.execute("PRAGMA table_info(prospects)")}
        score_info = list(conn.execute("PRAGMA table_info(scores)"))
        score_columns = {row[1]: row for row in score_info}
        assert "employee_count" in prospect_columns
        assert "page_embedding" in prospect_columns
        assert "page_embedding_model" in prospect_columns
        assert score_columns["score"][3] == 0
        assert "partial" in score_columns
        row = conn.execute(
            "SELECT score, breakdown_json, partial FROM scores WHERE id = 1"
        ).fetchone()
        assert row == (72.5, '{"title_fit": 100}', 0)
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
