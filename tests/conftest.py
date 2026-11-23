"""Shared isolated database fixture for Phase 2 tests."""

from __future__ import annotations

import pytest

from app import db


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "harvey-test.db"
    monkeypatch.setenv("DB_PATH", str(path))
    conn = db.connect()
    try:
        db.init_db(conn)
    finally:
        conn.close()
    return path
