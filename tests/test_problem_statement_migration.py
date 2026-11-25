from __future__ import annotations

import sqlite3

from app import db


def test_existing_problem_statements_table_gets_run_columns_and_source_backfill(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            docs_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            contact_name TEXT NOT NULL DEFAULT '',
            contact_title TEXT NOT NULL DEFAULT '',
            company_name TEXT NOT NULL DEFAULT '',
            company_domain TEXT NOT NULL DEFAULT '',
            employee_count INTEGER,
            contact_email TEXT NOT NULL DEFAULT '',
            page_text_path TEXT NOT NULL DEFAULT '',
            page_embedding BLOB,
            page_embedding_model TEXT NOT NULL DEFAULT '',
            do_not_contact INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE problem_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id INTEGER NOT NULL,
            statement TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO products (name, created_at, updated_at)
          VALUES ('Legacy product', '2026-01-01', '2026-01-01');
        INSERT INTO prospects (product_id, company_name, created_at)
          VALUES (1, 'Legacy prospect', '2026-01-01');
        INSERT INTO problem_statements (prospect_id, statement, created_at)
          VALUES (1, 'Existing saved problem', '2026-01-02');
        """
    )

    db.init_db(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(problem_statements)")}
    assert {
        "product_id",
        "business_profile_id",
        "icp_id",
        "signal_run_id",
        "source_signal_ids_json",
        "status",
        "evidence_json",
        "error",
        "model_name",
        "temperature",
        "seed",
        "repeat_penalty",
        "queue_task_id",
        "updated_at",
    } <= columns
    row = conn.execute("SELECT * FROM problem_statements WHERE id = 1").fetchone()
    values = dict(zip((item[1] for item in conn.execute("PRAGMA table_info(problem_statements)")), row))
    assert values["product_id"] == 1
    assert values["status"] == "succeeded"
    assert values["statement"] == "Existing saved problem"
    assert values["source_signal_ids_json"] == "[]"
    assert values["updated_at"] == "2026-01-02"
    conn.close()
