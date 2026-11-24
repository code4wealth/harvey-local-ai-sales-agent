from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app import db, llm_client
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker
from app.workflows import draft as draft_workflow


PROFILE = {
    "summary": "RelayCue: A local workspace helps support teams coordinate service handoffs.",
    "value_proposition": "Keeps service handoffs in one workspace.",
    "key_features": ["shared handoff notes"],
    "pain_points_solved": ["missed service handoffs"],
    "differentiators": ["not stated"],
    "typical_buyer": "support operations lead",
    "typical_team_size": "not stated",
    "working_situation": "Support teams coordinate service handoffs across shifts.",
    "not_for": ["not stated"],
}
QUOTE = "The team hired five support specialists this month."


def _post(path: str) -> httpx.Response:
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path)

    return asyncio.run(request())


def _get(path: str) -> httpx.Response:
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(request())


def _use_mock_transport(monkeypatch, handler) -> None:
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


def _response(value: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {"content": json.dumps(value, ensure_ascii=False)},
            "prompt_eval_count": 90,
            "eval_count": 30,
        },
    )


def _create_case(db_path, *, signals: list[dict] | None) -> tuple[int, int, int | None]:
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="Private stored product")
        prospect_id = db.create_prospect(
            conn,
            product_id=product_id,
            company_name="Private stored prospect",
            company_domain="private-prospect.example",
            contact_name="Private Contact",
            contact_title="Support Operations Director",
        )
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(PROFILE), "mock-profile", db.utcnow()),
        )
        conn.commit()
        signal_run_id = None
        if signals is not None:
            signal_run_id = db.create_signal_run(
                conn, prospect_id=prospect_id, model_name="mock-signals"
            )
            conn.execute(
                "UPDATE signal_runs SET status = 'succeeded', signals_json = ? "
                "WHERE id = ?",
                (json.dumps(signals, ensure_ascii=False), signal_run_id),
            )
            for signal in signals:
                conn.execute(
                    "INSERT INTO signals "
                    "(prospect_id, signal_run_id, type, evidence, confidence, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        prospect_id,
                        signal_run_id,
                        signal["type"],
                        signal["evidence"],
                        signal.get("confidence", 0.8),
                        db.utcnow(),
                    ),
                )
            conn.commit()
        return product_id, prospect_id, signal_run_id
    finally:
        conn.close()


def _verified_signal() -> dict:
    return {
        "type": "hiring",
        "evidence": QUOTE,
        "confidence": 0.8,
    }


def test_draft_schema_rejects_blank_or_multiline_subjects():
    with pytest.raises(ValueError):
        draft_workflow.OutreachDraft.model_validate(
            {"subject": "  ", "body": "Hello", "evidence_used": [QUOTE]}
        )
    with pytest.raises(ValueError, match="single line"):
        draft_workflow.OutreachDraft.model_validate(
            {"subject": "Hello\nInjected line", "body": "Hello", "evidence_used": [QUOTE]}
        )


def test_draft_uses_only_profile_and_verified_signals_and_is_never_sent(
    db_path, monkeypatch
):
    monkeypatch.setenv("DEFAULT_MODEL", "draft-test-model")
    product_id, prospect_id, signal_run_id = _create_case(
        db_path, signals=[_verified_signal()]
    )
    payloads = []
    calls = 0
    draft = {
        "subject": "A thought about shift handoffs",
        "body": f"I noticed this update: {QUOTE} RelayCue helps teams coordinate service handoffs.",
        "evidence_used": [QUOTE],
    }

    def handler(request):
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        payloads.append(payload)
        return _response(draft)

    _use_mock_transport(monkeypatch, handler)
    response = _post(
        f"/api/products/{product_id}/prospects/{prospect_id}/draft"
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "succeeded"
    assert result["product_id"] == product_id
    assert result["prospect_id"] == prospect_id
    assert result["subject"] == draft["subject"]
    assert result["body"] == draft["body"]
    assert result["evidence_used"] == [QUOTE]
    assert result["model_name"] == "draft-test-model"
    assert result["temperature"] == 0.0
    assert result["seed"] == 42
    assert result["signal_run_id"] == signal_run_id
    assert result["sent"] is False
    assert calls == 1
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["format"] == draft_workflow.OutreachDraft.model_json_schema()
    assert payload["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": draft_workflow.NUM_CTX,
    }
    prompt = payload["messages"][-1]["content"]
    assert "RelayCue: A local workspace" in prompt
    assert QUOTE in prompt
    assert "Private stored product" not in prompt
    assert "Private stored prospect" not in prompt
    assert "Private Contact" not in prompt
    assert "private-prospect.example" not in prompt
    assert _get(f"/api/products/{product_id}/prospects/{prospect_id}/draft").json() == result

    conn = db.connect()
    try:
        saved = db.get_draft_run(conn, result["id"])
        assert saved["status"] == "succeeded"
        assert saved["subject"] == draft["subject"]
        assert saved["body"] == draft["body"]
        assert json.loads(saved["evidence_used_json"]) == [QUOTE]
        assert conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
    finally:
        conn.close()


def test_draft_retries_unsupported_or_nonverbatim_evidence_then_persists_failure(
    db_path, monkeypatch
):
    product_id, prospect_id, _ = _create_case(db_path, signals=[_verified_signal()])
    outputs = [
        {
            "subject": "Unsupported evidence",
            "body": "This mentions a fictional funding round.",
            "evidence_used": ["A fictional funding round happened."],
        },
        {
            "subject": "Evidence missing from body",
            "body": "A brief note about the team.",
            "evidence_used": [QUOTE],
        },
        {
            "subject": "Still unsupported",
            "body": "The evidence does not appear here.",
            "evidence_used": ["Another invented quote."],
        },
    ]
    prompts = []
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return _response(outputs[calls - 1])

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/prospects/{prospect_id}/draft")

    assert response.status_code == 502
    result = response.json()
    assert result["status"] == "failed"
    assert result["subject"] is None
    assert result["body"] is None
    assert result["evidence_used"] is None
    assert "InvalidJsonResponse" in result["error"]
    assert calls == 3
    assert "previous answer was invalid" in prompts[1]
    assert "previous answer was invalid" in prompts[2]
    assert _get(f"/api/products/{product_id}/prospects/{prospect_id}/draft").json() == result
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
        row = db.get_draft_run(conn, result["id"])
        assert row["status"] == "failed"
        assert row["subject"] is None and row["body"] is None
    finally:
        conn.close()


def test_no_verified_signals_skips_llm_and_persists_reason(db_path, monkeypatch):
    product_id, prospect_id, _ = _create_case(db_path, signals=None)
    conn = db.connect()
    try:
        # A completed empty signal extraction is still no usable evidence.
        empty_run = db.create_signal_run(
            conn, prospect_id=prospect_id, model_name="mock-signals"
        )
        conn.execute(
            "UPDATE signal_runs SET status = 'succeeded', signals_json = '[]' WHERE id = ?",
            (empty_run,),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        llm_client,
        "generate_json",
        lambda *args, **kwargs: pytest.fail("drafting must skip the LLM without verified signals"),
    )
    monkeypatch.setattr(
        llm_client,
        "resolve_model_name",
        lambda *_args: pytest.fail("model resolution is unnecessary when evidence is missing"),
    )
    response = _post(f"/api/products/{product_id}/prospects/{prospect_id}/draft")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "skipped"
    assert result["reason"] == "no verified evidence"
    assert result["subject"] is None
    assert result["body"] is None
    assert result["evidence_used"] is None
    assert result["signal_run_id"] == empty_run
    assert result["sent"] is False
    assert _get(f"/api/products/{product_id}/prospects/{prospect_id}/draft").json() == result
    conn = db.connect()
    try:
        stored = db.get_draft_run(conn, result["id"])
        assert stored["status"] == "skipped"
        assert stored["error"] == "no verified evidence"
        assert conn.execute("SELECT COUNT(*) FROM inference_log").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
    finally:
        conn.close()


def test_unavailable_ollama_queues_and_worker_replays_draft(db_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "queued-draft-model")
    product_id, prospect_id, _ = _create_case(db_path, signals=[_verified_signal()])

    def unavailable(request):
        raise httpx.ConnectError("mocked local outage", request=request)

    _use_mock_transport(monkeypatch, unavailable)
    queued_response = _post(f"/api/products/{product_id}/prospects/{prospect_id}/draft")
    assert queued_response.status_code == 202
    queued = queued_response.json()
    assert queued["status"] == "queued"
    assert queued["queue_task_id"] is not None
    assert queued["sent"] is False

    conn = db.connect()
    try:
        task = db.get_task(conn, queued["queue_task_id"])
        task_payload = json.loads(task["payload_json"])
        assert task["status"] == "queued"
        assert task_payload == {
            "draft_run_id": queued["id"],
            "product_id": product_id,
            "prospect_id": prospect_id,
            "model_name": "queued-draft-model",
        }
    finally:
        conn.close()

    healthy_draft = {
        "subject": "Support for the new team",
        "body": f"I saw this update: {QUOTE}",
        "evidence_used": [QUOTE],
    }
    _use_mock_transport(monkeypatch, lambda _request: _response(healthy_draft))
    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    previous = HANDLERS.get(draft_workflow.TASK_TYPE)
    draft_workflow.register_draft_handler()
    try:
        assert QueueWorker().run_once() == 1
    finally:
        if previous is None:
            HANDLERS.pop(draft_workflow.TASK_TYPE, None)
        else:
            HANDLERS[draft_workflow.TASK_TYPE] = previous

    completed = _get(f"/api/products/{product_id}/prospects/{prospect_id}/draft").json()
    assert completed["status"] == "succeeded"
    assert completed["body"] == healthy_draft["body"]
    assert completed["sent"] is False
    conn = db.connect()
    try:
        assert db.get_task(conn, queued["queue_task_id"])["status"] == "done"
        assert conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
    finally:
        conn.close()
