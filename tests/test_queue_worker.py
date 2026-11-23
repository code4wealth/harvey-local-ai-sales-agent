from __future__ import annotations

import httpx

from app.db import enqueue_task, get_task
from app.llm_client import OllamaClient, OllamaUnavailable
from app.queue_worker import QueueWorker


def test_queue_worker_retries_when_local_inference_returns(tmp_path):
    results = ["down", "down", "ready"]

    def respond(request: httpx.Request) -> httpx.Response:
        result = results.pop(0)
        if result == "down":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"response": "Queued result"})

    db_path = tmp_path / "harvey.db"
    client = OllamaClient(
        db_path=db_path,
        default_model="qwen3:4b",
        transport=httpx.MockTransport(respond),
    )
    try:
        queued_task_id = None
        try:
            client.generate_or_queue(
                task="profile",
                prompt="Local product facts.",
                max_attempts=3,
            )
        except OllamaUnavailable as queued_error:
            queued_task_id = queued_error.task_id
            assert queued_task_id is not None
        else:
            raise AssertionError("The unavailable task should have been queued.")

        worker = QueueWorker(
            db_path=str(db_path),
            llm_client=client,
            retry_base_seconds=0,
            retry_max_seconds=0,
        )
        task_id = queued_task_id
        assert worker.run_once() is True
        requeued = get_task(task_id, db_path=db_path)
        assert requeued["status"] == "queued"
        assert requeued["attempts"] == 1
        assert "127.0.0.1:11434" in requeued["last_error"]

        assert worker.run_once() is True
        completed = get_task(task_id, db_path=db_path)
        assert completed["status"] == "completed"
        assert completed["attempts"] == 2
        assert completed["result"] == "Queued result"
        assert worker.run_once() is False
    finally:
        client.close()


def test_queue_worker_runs_registered_deterministic_handler(tmp_path):
    db_path = tmp_path / "harvey.db"
    task_id = enqueue_task("sample", {"value": 6}, db_path=db_path)
    worker = QueueWorker(
        db_path=str(db_path),
        handlers={"sample": lambda payload: {"doubled": payload["value"] * 2}},
    )

    assert worker.run_once() is True
    task = get_task(task_id, db_path=db_path)
    assert task["status"] == "completed"
    assert task["result"] == {"doubled": 12}


def test_queue_worker_fails_unhandled_task_clearly(tmp_path):
    db_path = tmp_path / "harvey.db"
    task_id = enqueue_task("unhandled", {}, db_path=db_path)
    worker = QueueWorker(db_path=str(db_path))

    assert worker.run_once() is True
    task = get_task(task_id, db_path=db_path)
    assert task["status"] == "failed"
    assert "No handler registered" in task["last_error"]
