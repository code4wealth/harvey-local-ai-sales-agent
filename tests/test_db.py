from __future__ import annotations

import sqlite3

import pytest

from app.db import (
    create_product,
    get_product,
    init_db,
    list_products,
    list_inference_logs,
    record_inference,
)


def test_database_initializes_required_foundation_tables(tmp_path):
    db_path = tmp_path / "harvey.db"
    init_db(db_path)
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"products", "task_queue", "inference_log"} <= tables


def test_product_helpers_create_list_and_fetch(tmp_path):
    db_path = tmp_path / "harvey.db"
    product_id = create_product(
        "Sample product",
        description="SAMPLE description",
        company_info_path="data/company_info/sample",
        db_path=db_path,
    )
    assert get_product(product_id, db_path=db_path)["name"] == "Sample product"
    assert list_products(db_path=db_path)[0]["description"] == "SAMPLE description"


def test_product_name_is_required_and_unique(tmp_path):
    db_path = tmp_path / "harvey.db"
    with pytest.raises(ValueError, match="must not be blank"):
        create_product("  ", db_path=db_path)
    create_product("Harvey", db_path=db_path)
    with pytest.raises(sqlite3.IntegrityError):
        create_product("harvey", db_path=db_path)


def test_inference_log_accepts_only_the_local_host(tmp_path):
    db_path = tmp_path / "harvey.db"
    record_inference(
        task="profile",
        model="qwen3:4b",
        prompt_tokens=10,
        eval_tokens=4,
        latency_seconds=0.25,
        status="success",
        tokens_per_second=2.0,
        db_path=db_path,
    )
    log = list_inference_logs(db_path=db_path)[0]
    assert log["host"] == "http://127.0.0.1:11434"
    assert log["tokens_per_second"] == 2.0
    with pytest.raises(ValueError, match="fixed local"):
        record_inference(
            task="profile",
            model="qwen3:4b",
            prompt_tokens=None,
            eval_tokens=None,
            latency_seconds=0,
            status="success",
            host="https://not-local.invalid",
            db_path=db_path,
        )


def test_init_db_migrates_existing_inference_log_for_throughput(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE inference_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                model TEXT NOT NULL,
                host TEXT NOT NULL,
                prompt_tokens INTEGER,
                eval_tokens INTEGER,
                latency_seconds REAL NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            )"""
        )

    init_db(db_path)
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(inference_log)")
        }
    assert "tokens_per_second" in columns
