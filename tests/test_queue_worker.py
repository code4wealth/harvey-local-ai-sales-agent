from __future__ import annotations

import asyncio
import threading

import httpx
import pytest

from app import db, llm_client
from app.main import app
from app.llm_client import OllamaTimeout, OllamaUnavailable
from app.queue_worker import HANDLERS, QueueWorker, register_handler
import app.queue_worker as queue_worker


def test_fastapi_lifespan_starts_and_stops_background_worker(db_path, monkeypatch):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    def client_factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", client_factory)

    async def exercise_lifespan():
        async with app.router.lifespan_context(app):
            worker = app.state.queue_worker
            assert worker._thread is not None
            assert worker._thread.is_alive()
        assert not worker._thread.is_alive()

    asyncio.run(exercise_lifespan())


def test_queue_worker_survives_read_timeout_from_health_probe(db_path, monkeypatch):
    probe_called = threading.Event()

    def slow_probe(request):
        assert request.url.path == "/api/tags"
        probe_called.set()
        raise httpx.ReadTimeout("probe delayed", request=request)

    def client_factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(slow_probe),
        )

    monkeypatch.setattr(llm_client, "_client", client_factory)
    register_handler("test.requires_ollama", lambda payload: None)
    conn = db.connect()
    try:
        db.enqueue_task(conn, "test.requires_ollama", {})
    finally:
        conn.close()
    worker = QueueWorker(poll_seconds=0.05)
    worker.start()
    try:
        assert probe_called.wait(timeout=2.0)
        assert worker._thread is not None and worker._thread.is_alive()
    finally:
        worker.stop(timeout=2.0)
        HANDLERS.pop("test.requires_ollama", None)
    assert worker._thread is not None and not worker._thread.is_alive()


def test_unknown_queue_task_fails_visibly_without_ollama_probe(db_path, monkeypatch, caplog):
    monkeypatch.setattr(
        queue_worker, "ollama_up", lambda: pytest.fail("unknown task must not probe Ollama")
    )
    conn = db.connect()
    try:
        task_id = db.enqueue_task(conn, "unknown.task.type", {}, max_attempts=3)
    finally:
        conn.close()

    assert QueueWorker().run_once() == 1
    conn = db.connect()
    try:
        row = db.get_task(conn, task_id)
        assert row["status"] == "failed"
        assert row["attempts"] == 1
        assert "no handler registered" in row["last_error"]
        assert db.queue_counts(conn)["done"] == 0
    finally:
        conn.close()
    assert "no handler registered" in caplog.text


def test_queue_worker_retries_then_fails_without_deleting_task(db_path, monkeypatch):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    def client_factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", client_factory)
    task_type = "test.always_fails"
    calls = []

    def deterministic_test_handler(payload):
        calls.append(payload)
        raise ValueError("test failure")

    register_handler(task_type, deterministic_test_handler)
    conn = db.connect()
    try:
        task_id = db.enqueue_task(conn, task_type, {"sample": 7}, max_attempts=2)
    finally:
        conn.close()

    try:
        worker = QueueWorker(poll_seconds=0.01)
        assert worker.run_once() == 1
        conn = db.connect()
        try:
            row = db.get_task(conn, task_id)
            assert row["status"] == "queued"
            assert row["attempts"] == 1
            assert row["last_error"] == "ValueError: test failure"
        finally:
            conn.close()

        assert worker.run_once() == 1
        conn = db.connect()
        try:
            row = db.get_task(conn, task_id)
            assert row["status"] == "failed"
            assert row["attempts"] == 2
            assert row["last_error"] == "ValueError: test failure"
            assert db.queue_counts(conn)["failed"] == 1
        finally:
            conn.close()
        assert calls == [{"sample": 7}, {"sample": 7}]
    finally:
        HANDLERS.pop(task_type, None)


@pytest.mark.parametrize("error_type", [OllamaUnavailable, OllamaTimeout])
def test_queue_worker_requeues_unavailable_and_slow_model_errors(db_path, monkeypatch, error_type):
    def probe(request):
        return httpx.Response(200, json={"models": []})

    def client_factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(probe),
        )

    monkeypatch.setattr(llm_client, "_client", client_factory)
    task_type = f"test.retry.{error_type.__name__}"

    def unavailable_handler(payload):
        raise error_type("retry this task")

    register_handler(task_type, unavailable_handler)
    conn = db.connect()
    try:
        task_id = db.enqueue_task(conn, task_type, {}, max_attempts=2)
    finally:
        conn.close()

    try:
        assert QueueWorker().run_once() == 1
        conn = db.connect()
        try:
            row = db.get_task(conn, task_id)
            assert row["status"] == "queued"
            assert row["attempts"] == 1
            assert row["last_error"].startswith(f"{error_type.__name__}:")
        finally:
            conn.close()
    finally:
        HANDLERS.pop(task_type, None)
