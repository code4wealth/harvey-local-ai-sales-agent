"""Shared isolated database fixture for Phase 2 tests."""

from __future__ import annotations

import os

import httpx
import pytest

from app import db


_TEST_INSTALLED_MODELS = {
    "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b",
    "draft-test-model", "empty-signals", "failed-signals", "failure-test-model",
    "icp-colon-model", "icp-grounding-model", "icp-specific-failure-model",
    "icp-stray-token-model", "legacy-model", "mock-local-model", "mock-model",
    "mock-reply-evaluator", "mock-signals", "old-model", "pipeline-test-model",
    "pollable-profile-model", "problem-test-model", "product-name-check-model",
    "profile-colon-model", "profile-grounding-model", "profile-stray-token-model",
    "queued-draft-model", "queued-problem-model", "queued-test-model",
    "reply-test-model", "retry-test-model", "sample-test-model", "separation-test-model",
    "signal-invalid-model", "signal-negation-model", "signal-queue-model",
    "signal-quote-model", "signal-quote-retry-model", "signal-retry-model",
    "signal-stray-token-model", "signal-test-model", "signal-trap-model",
    "signal-verbatim-model", "test-model", "mock-profile-model",
}


def mock_ollama_handler(handler):
    """Provide a stable local /api/tags inventory for inference unit tests."""
    def route(request):
        if request.url.path == "/api/tags":
            models = set(_TEST_INSTALLED_MODELS)
            configured = os.environ.get("DEFAULT_MODEL", "").strip()
            if configured:
                models.add(configured)
            return httpx.Response(
                200,
                json={"models": [{"name": name} for name in sorted(models)]},
            )
        return handler(request)

    return route


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
