from __future__ import annotations

import asyncio

import httpx

from app import db, llm_client
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker, register_handler


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
