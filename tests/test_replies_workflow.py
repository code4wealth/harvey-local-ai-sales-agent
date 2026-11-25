from __future__ import annotations

import asyncio
import csv
import hashlib
import json

import httpx
import pytest
from pydantic import ValidationError

from conftest import mock_ollama_handler
from app import db, llm_client
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker
from app.workflows import replies as reply_workflow
from scripts import import_replies


def _use_mock_transport(monkeypatch, handler) -> None:
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(mock_ollama_handler(handler)),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


def _post(path: str) -> httpx.Response:
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            return await client.post(path)

    return asyncio.run(request())


def _get(path: str) -> httpx.Response:
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            return await client.get(path)

    return asyncio.run(request())


def _store_reply(reply_id: str, text: str) -> None:
    conn = db.connect()
    try:
        db.init_db(conn)
        db.upsert_sample_replies(conn, [{"reply_id": reply_id, "text": text}])
    finally:
        conn.close()


def test_reply_importer_persists_text_only_rows(db_path, tmp_path):
    csv_path = tmp_path / "replies.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reply_id", "text"])
        writer.writerows(
            (f"R{number:03d}", f"Synthetic test reply {number}.")
            for number in range(1, 61)
        )

    assert import_replies.import_replies(csv_path, str(db_path)) == 60
    conn = db.connect()
    try:
        rows = db.list_sample_replies(conn)
        assert len(rows) == 60
        assert rows[0]["reply_id"] == "R001"
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sample_replies)")}
        assert columns == {"reply_id", "reply_text", "created_at", "updated_at"}
    finally:
        conn.close()


def _response(label: str = "interested") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {
                "content": (
                    "```json\n"
                    + json.dumps(
                        {"label": label, "confidence": 0.91, "rationale": "A clear response."}
                    )
                    + "\n```"
                )
            },
            "prompt_eval_count": 100,
            "eval_count": 18,
        },
    )


def test_sample_reply_import_endpoint_is_idempotent_and_text_only(db_path):
    first = _post("/api/replies/import-sample")
    second = _post("/api/replies/import-sample")

    assert first.status_code == 200
    assert first.json() == {"imported": 60, "source": "sample replies"}
    assert second.status_code == 200
    assert second.json() == first.json()
    conn = db.connect()
    try:
        rows = db.list_sample_replies(conn)
        assert len(rows) == 60
        assert {row["reply_id"] for row in rows} == {f"R{number:03d}" for number in range(1, 61)}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sample_replies)")}
        assert columns == {"reply_id", "reply_text", "created_at", "updated_at"}
    finally:
        conn.close()


def test_sample_reply_import_endpoint_reports_invalid_bundled_csv(monkeypatch, db_path):
    def fail_import():
        raise ValueError("CSV row is malformed")

    monkeypatch.setattr(import_replies, "import_replies", fail_import)
    response = _post("/api/replies/import-sample")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Sample replies could not be imported; check the bundled CSV."
    }


def test_reply_schema_enforces_labels_confidence_and_rationale_length():
    result = reply_workflow.ReplyClassification.model_validate(
        {"label": "question", "confidence": 0.5, "rationale": "Asks for details."}
    )
    assert result.label == "question"
    with pytest.raises(ValidationError):
        reply_workflow.ReplyClassification.model_validate(
            {"label": "unknown", "confidence": 0.5, "rationale": "Invalid label."}
        )
    with pytest.raises(ValidationError):
        reply_workflow.ReplyClassification.model_validate(
            {"label": "other", "confidence": 1.1, "rationale": "Out of range."}
        )
    with pytest.raises(ValidationError):
        reply_workflow.ReplyClassification.model_validate(
            {"label": "other", "confidence": 0.5, "rationale": "x" * 201}
        )


def test_classification_receives_only_reply_text_and_stores_result(db_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "reply-test-model")
    reply_text = "Would your team want a short overview next Thursday?"
    _store_reply("R001", reply_text)
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return _response("meeting_request")

    _use_mock_transport(monkeypatch, handler)
    response = _post("/api/replies/R001/classification")

    assert response.status_code == 200
    body = response.json()
    assert body["reply_id"] == "R001"
    assert body["status"] == "succeeded"
    assert body["label"] == "meeting_request"
    assert body["confidence"] == pytest.approx(0.91)
    assert body["model_name"] == "reply-test-model"
    assert body["temperature"] == 0.0
    assert body["seed"] == 42
    assert body["created_at"] and body["updated_at"]
    assert "reply_text" not in body
    assert _get("/api/replies/R001/classification").json() == body

    assert len(seen) == 1
    payload = seen[0]
    assert payload["format"] == reply_workflow.ReplyClassification.model_json_schema()
    assert payload["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": reply_workflow.NUM_CTX,
    }
    prompt = payload["messages"][-1]["content"]
    expected_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert body["prompt_hash"] == expected_prompt_hash
    assert body["commit_hash"]
    assert reply_text in prompt
    assert "not now" in prompt
    assert "question: asks a specific question about how the product works" in prompt
    assert "willingness to see material or talk is interested" in prompt
    assert "wrong_person: says the sender is not the right contact or does not own the topic" in prompt
    assert "a polite decline with referral is still wrong_person" in prompt
    assert "an automatic away message is out_of_office" in prompt
    assert "other: anything that fits no other label" in prompt
    assert "confusion about why the message arrived" in prompt
    assert "a misdirected or shared mailbox" in prompt
    assert "or an unclear reply" in prompt
    assert prompt.count('{\"label\":') == 1
    assert "alternate-contact referral" in prompt
    assert "politely or directly asks" in prompt
    assert "R001" not in prompt
    assert "ground_truth_label" not in prompt
    assert "difficulty" not in prompt
    assert "split" not in prompt
    assert "fictional observatory" in prompt
    conn = db.connect()
    try:
        saved = db.get_reply_classification(conn, "R001")
        assert saved["prompt_hash"] == expected_prompt_hash
        assert saved["commit_hash"] == body["commit_hash"]
    finally:
        conn.close()


def test_bad_label_retries_then_returns_valid_classification(db_path, monkeypatch):
    _store_reply("R002", "Please send a concise overview of the service.")
    replies = iter(
        [
            '{"label":"prospect","confidence":0.8,"rationale":"Unknown class."}',
            '{"label":"question","confidence":0.88,"rationale":"Requests an overview."}',
        ]
    )
    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return httpx.Response(200, json={"message": {"content": next(replies)}})

    _use_mock_transport(monkeypatch, handler)
    result = reply_workflow.submit_reply_classification("R002", model="qwen3:4b")

    assert result["status"] == "succeeded"
    assert result["label"] == "question"
    assert len(prompts) == 2
    assert "previous answer was invalid" in prompts[1]


def test_classifier_failure_is_persisted_without_a_default_label(db_path, monkeypatch):
    _store_reply("R003", "We will review the proposal later.")
    calls = []

    def handler(_request):
        calls.append(1)
        return httpx.Response(200, json={"message": {"content": "not json"}})

    _use_mock_transport(monkeypatch, handler)
    response = _post("/api/replies/R003/classification")

    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert body["label"] is None
    assert body["confidence"] is None
    assert "InvalidJsonResponse" in body["error"]
    assert len(calls) == 2
    assert _get("/api/replies/R003/classification").json() == body


def test_ollama_unavailable_queues_and_replays_classification(db_path, monkeypatch):
    _store_reply("R004", "Please contact me again in the autumn.")

    def unavailable(request):
        raise httpx.ConnectError("mocked local outage", request=request)

    _use_mock_transport(monkeypatch, unavailable)
    queued_response = _post("/api/replies/R004/classification")
    assert queued_response.status_code == 202
    queued = queued_response.json()
    assert queued["status"] == "queued"
    assert queued["label"] is None
    assert queued["queue_task_id"] is not None

    conn = db.connect()
    try:
        task = db.get_task(conn, queued["queue_task_id"])
        assert json.loads(task["payload_json"]) == {
            "reply_id": "R004",
            "model_name": queued["model_name"],
        }
    finally:
        conn.close()

    _use_mock_transport(monkeypatch, lambda _request: _response("interested"))
    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    previous = HANDLERS.get(reply_workflow.TASK_TYPE)
    reply_workflow.register_reply_handler()
    try:
        assert QueueWorker().run_once() == 1
    finally:
        if previous is None:
            HANDLERS.pop(reply_workflow.TASK_TYPE, None)
        else:
            HANDLERS[reply_workflow.TASK_TYPE] = previous

    completed = _get("/api/replies/R004/classification").json()
    assert completed["status"] == "succeeded"
    assert completed["label"] == "interested"
    conn = db.connect()
    try:
        assert db.get_task(conn, queued["queue_task_id"])["status"] == "done"
    finally:
        conn.close()
