import json
import sqlite3

import pytest

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
        for table in (
            "workflow_runs", "signal_runs", "reply_classifications", "inference_log",
            "draft_runs", "problem_statements",
        ):
            assert {"prompt_hash", "commit_hash"} <= {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
        for table in ("business_profiles", "icps"):
            assert {"temperature", "seed", "repeat_penalty", "prompt_hash", "commit_hash"} <= {
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
        assert {"temperature", "seed", "prompt_hash", "commit_hash"} <= columns
        row = conn.execute(
            "SELECT status, load_seconds, temperature, seed, prompt_hash, commit_hash "
            "FROM inference_log"
        ).fetchone()
        assert row == ("ok", None, 0.0, 42, "", "")
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
            assert {
                "model_name", "temperature", "seed", "repeat_penalty", "prompt_hash", "commit_hash"
            } <= columns
            assert conn.execute(
                f"SELECT model_name, temperature, seed, repeat_penalty, prompt_hash, commit_hash "
                f"FROM {table} WHERE id = 1"
            ).fetchone() == ("", 0.0, 42, 1.0, "", "")
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


def test_init_db_merges_casefold_duplicate_products_and_repoints_all_records(tmp_path):
    conn = sqlite3.connect(tmp_path / "duplicate-products.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(db.SCHEMA)
        now = "2026-01-01T00:00:00Z"
        later = "2026-01-02T00:00:00Z"
        conn.executemany(
            "INSERT INTO products (id, name, description, docs_path, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "Dairy Milk", "", "", now, now),
                (2, "  dAiRy mIlK  ", "merged description", "company.md", later, later),
            ],
        )
        conn.execute(
            "INSERT INTO prospects (id, product_id, company_name, created_at) VALUES (10, 2, 'Acme', ?) ",
            (later,),
        )
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (2, '{\"summary\":\"saved\"}', 'qwen3:4b', ?)",
            (later,),
        )
        conn.execute(
            "INSERT INTO icps (product_id, icp_json, model_name, created_at) "
            "VALUES (2, '{\"industries\":[]}', 'qwen3:4b', ?)",
            (later,),
        )
        conn.execute(
            "INSERT INTO signal_runs (id, prospect_id, product_id, status, created_at, updated_at) "
            "VALUES (20, 10, 2, 'succeeded', ?, ?)",
            (later, later),
        )
        conn.execute(
            "INSERT INTO signals (prospect_id, signal_run_id, type, evidence, confidence, created_at) "
            "VALUES (10, 20, 'hiring', 'stored evidence', 0.9, ?)",
            (later,),
        )
        conn.execute(
            "INSERT INTO workflow_runs (id, product_id, workflow, status, created_at, updated_at) "
            "VALUES (30, 2, 'profile', 'queued', ?, ?)",
            (later, later),
        )
        task_id = db.enqueue_task(
            conn,
            "workflow.profile",
            {"product_id": 2, "workflow_run_id": 30, "model_name": "qwen3:4b"},
        )
        conn.execute("UPDATE workflow_runs SET queue_task_id = ? WHERE id = 30", (task_id,))
        conn.execute(
            "INSERT INTO draft_runs (product_id, prospect_id, status, subject, body, created_at, updated_at) "
            "VALUES (2, 10, 'succeeded', 'Subject', 'Body', ?, ?)",
            (later, later),
        )
        conn.execute(
            "INSERT INTO problem_statements (product_id, prospect_id, status, statement, created_at, updated_at) "
            "VALUES (2, 10, 'succeeded', 'Problem', ?, ?)",
            (later, later),
        )
        conn.execute(
            "INSERT INTO replies (prospect_id, reply_text, label, confidence, created_at) "
            "VALUES (10, 'Reply text', 'interested', 0.9, ?)",
            (later,),
        )
        conn.execute(
            "INSERT INTO emails (prospect_id, subject, body, word_count, created_at) "
            "VALUES (10, 'Saved draft', 'Stored draft body', 3, ?)",
            (later,),
        )
        conn.execute(
            "INSERT INTO pipeline_runs (product_id, status, created_at) VALUES (2, 'queued', ?)",
            (later,),
        )
        conn.commit()

        db.init_db(conn)

        products = conn.execute("SELECT id, name, description, docs_path FROM products").fetchall()
        assert [tuple(row) for row in products] == [(1, "Dairy Milk", "merged description", "company.md")]
        for table in (
            "business_profiles", "icps", "prospects", "signal_runs", "workflow_runs",
            "draft_runs", "problem_statements", "pipeline_runs",
        ):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE product_id = 1").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM prospects WHERE product_id = 2").fetchone()[0] == 0
        assert conn.execute("SELECT prospect_id FROM signals").fetchone()[0] == 10
        assert conn.execute("SELECT signal_run_id FROM signals").fetchone()[0] == 20
        assert conn.execute("SELECT prospect_id FROM draft_runs").fetchone()[0] == 10
        assert conn.execute("SELECT prospect_id FROM replies").fetchone()[0] == 10
        assert conn.execute("SELECT prospect_id FROM emails").fetchone()[0] == 10
        problem = conn.execute("SELECT product_id, prospect_id FROM problem_statements").fetchone()
        assert tuple(problem) == (1, 10)
        payload = conn.execute("SELECT payload_json FROM task_queue WHERE id = ?", (task_id,)).fetchone()[0]
        assert json.loads(payload)["product_id"] == 1
        assert json.loads(payload)["workflow_run_id"] == 30
        assert conn.execute("SELECT product_id FROM workflow_runs WHERE id = 30").fetchone()[0] == 1

        # Every product reference must point to the retained row; prospect/run
        # relationships must remain valid across the merge, not merely present.
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in table_names:
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            if "product_id" in columns and table != "products":
                assert conn.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE product_id = 2'
                ).fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute(
            "SELECT COUNT(*) FROM signals s "
            "LEFT JOIN prospects p ON p.id = s.prospect_id "
            "LEFT JOIN signal_runs r ON r.id = s.signal_run_id "
            "WHERE p.id IS NULL OR r.id IS NULL OR r.prospect_id != s.prospect_id "
            "OR r.product_id != p.product_id"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM draft_runs d LEFT JOIN prospects p ON p.id = d.prospect_id "
            "WHERE p.id IS NULL OR d.product_id != p.product_id"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM workflow_runs r LEFT JOIN products p ON p.id = r.product_id "
            "WHERE p.id IS NULL"
        ).fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
            conn.execute(
                "INSERT INTO products (name, created_at, updated_at) VALUES ('DAIRY MILK', ?, ?)",
                (later, later),
            )
    finally:
        conn.close()


def test_init_db_migrates_pipeline_progress_columns_on_existing_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy-pipeline.db")
    try:
        conn.executescript(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
            "CREATE TABLE prospects (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL);"
            "CREATE TABLE pipeline_runs (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, "
            "status TEXT NOT NULL, started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL);"
            "CREATE TABLE pipeline_steps (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, "
            "step_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', last_error TEXT, "
            "started_at TEXT, finished_at TEXT, UNIQUE(run_id, step_name));"
            "INSERT INTO products VALUES (1, 'Legacy product');"
            "INSERT INTO prospects VALUES (2, 1);"
            "INSERT INTO pipeline_runs VALUES (3, 1, 'queued', NULL, NULL, 'then');"
            "INSERT INTO pipeline_steps VALUES (4, 3, 'profile', 'queued', NULL, NULL, NULL);"
        )

        db.init_db(conn)

        run_columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)")}
        step_columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_steps)")}
        assert {"model_name", "queue_task_id"} <= run_columns
        assert {"step_order", "prospect_id", "result_json"} <= step_columns
        row = conn.execute(
            "SELECT step_order, prospect_id, result_json FROM pipeline_steps WHERE id = 4"
        ).fetchone()
        assert tuple(row) == (0, None, "{}")
    finally:
        conn.close()
