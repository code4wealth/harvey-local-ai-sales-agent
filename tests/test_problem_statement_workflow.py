from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest

from app import db, llm_client
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker
from app.workflows import problem_statement as problem_workflow


PROFILE = {
    "summary": "RelayCue coordinates support service handoffs across shifts.",
    "value_proposition": "Keeps service handoffs in one workspace.",
    "key_features": ["shared handoff notes"],
    "pain_points_solved": ["missed service handoffs"],
    "differentiators": ["not stated"],
    "typical_buyer": "support operations lead",
    "typical_team_size": "not stated",
    "working_situation": "Support teams coordinate service handoffs across shifts.",
    "not_for": ["not stated"],
}
ICP = {
    "industries": ["service handoffs"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["support operations lead"],
    "pain_points": ["missed service handoffs"],
    "trigger_events": ["not stated"],
    "disqualifiers": ["not stated"],
}
SIGNAL_EVIDENCE = "The team hired five support specialists this month."
EVIDENCE_SPAN = "The team hired five support specialists"
STATEMENT = (
    "The team hired five support specialists this month, which may increase "
    "coordination needs across service handoffs."
)


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


def _create_case(db_path, *, signals: list[dict] | None):
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="Stored product")
        prospect_id = db.create_prospect(
            conn,
            product_id=product_id,
            company_name="Stored prospect",
            company_domain="stored-prospect.example",
        )
        cursor = conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(PROFILE), "mock-profile", db.utcnow()),
        )
        profile_id = int(cursor.lastrowid)
        cursor = conn.execute(
            "INSERT INTO icps (product_id, icp_json, embedding, embedding_model, model_name, created_at) "
            "VALUES (?, ?, NULL, '', ?, ?)",
            (product_id, json.dumps(ICP), "mock-icp", db.utcnow()),
        )
        icp_id = int(cursor.lastrowid)
        conn.commit()

        signal_run_id = None
        signal_ids: list[int] = []
        if signals is not None:
            signal_run_id = db.create_signal_run(
                conn, prospect_id=prospect_id, model_name="mock-signals"
            )
            conn.execute(
                "UPDATE signal_runs SET status = 'succeeded', signals_json = ? WHERE id = ?",
                (json.dumps(signals, ensure_ascii=False), signal_run_id),
            )
            for signal in signals:
                cursor = conn.execute(
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
                signal_ids.append(int(cursor.lastrowid))
            conn.commit()
        return product_id, prospect_id, profile_id, icp_id, signal_run_id, signal_ids
    finally:
        conn.close()


def _verified_signal() -> dict:
    return {"type": "hiring", "evidence": SIGNAL_EVIDENCE, "confidence": 0.8}


def _path(product_id: int, prospect_id: int) -> str:
    return f"/api/products/{product_id}/prospects/{prospect_id}/problem-statement"


def test_problem_statement_uses_latest_profile_icp_and_verified_signal_sources(
    db_path, monkeypatch
):
    monkeypatch.setenv("DEFAULT_MODEL", "problem-test-model")
    product_id, prospect_id, profile_id, icp_id, signal_run_id, signal_ids = _create_case(
        db_path, signals=[_verified_signal()]
    )
    # A newer failed run must not displace the latest successful signal snapshot.
    conn = db.connect()
    try:
        newer = db.create_signal_run(conn, prospect_id=prospect_id, model_name="failed-signals")
        conn.execute("UPDATE signal_runs SET status = 'failed' WHERE id = ?", (newer,))
        conn.commit()
    finally:
        conn.close()

    payloads = []
    output = {"statement": STATEMENT, "evidence": [EVIDENCE_SPAN]}

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        return _response(output)

    _use_mock_transport(monkeypatch, handler)
    response = _post(_path(product_id, prospect_id))

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "succeeded"
    assert result["statement"] == STATEMENT
    assert result["evidence"] == [EVIDENCE_SPAN]
    assert result["model_name"] == "problem-test-model"
    assert result["temperature"] == 0.0
    assert result["seed"] == 42
    assert result["repeat_penalty"] == 1.0
    assert result["business_profile_id"] == profile_id
    assert result["icp_id"] == icp_id
    assert result["signal_run_id"] == signal_run_id
    assert result["source_signal_ids"] == signal_ids
    assert result["queue_task_id"] is None
    assert _get(_path(product_id, prospect_id)).json() == result

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["format"] == problem_workflow.GeneratedProblemStatement.model_json_schema()
    evidence_schema = payload["format"]["properties"]["evidence"]["items"]
    assert evidence_schema["pattern"] == problem_workflow.EVIDENCE_SPAN_PATTERN
    assert payload["format"]["properties"]["evidence"]["minItems"] == 1
    assert payload["format"]["properties"]["evidence"]["maxItems"] == 2
    assert payload["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": problem_workflow.NUM_CTX,
    }
    prompt = payload["messages"][-1]["content"]
    expected_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert result["prompt_hash"] == expected_prompt_hash
    assert result["commit_hash"]
    assert "Stored business profile JSON" in prompt
    assert "Stored ICP JSON" in prompt
    assert "Verified signals JSON" in prompt
    assert PROFILE["summary"] in prompt
    assert "service handoffs" in prompt
    assert SIGNAL_EVIDENCE in prompt
    assert "Stored product" not in prompt
    assert "Stored prospect" not in prompt

    conn = db.connect()
    try:
        row = db.get_problem_statement_run(conn, result["id"])
        assert row["status"] == "succeeded"
        assert row["prompt_hash"] == expected_prompt_hash
        assert row["commit_hash"] == result["commit_hash"]
        assert row["statement"] == STATEMENT
        assert json.loads(row["evidence_json"]) == [EVIDENCE_SPAN]
        assert json.loads(row["source_signal_ids_json"]) == signal_ids
    finally:
        conn.close()


def test_problem_statement_validation_only_normalizes_case_and_whitespace():
    valid = problem_workflow.GeneratedProblemStatement.model_validate(
        {
            "statement": "THE\tteam hired five support specialists this month.",
            "evidence": ["the team hired five support specialists"],
        }
    )
    problem_workflow.validate_problem_statement_evidence(valid, [_verified_signal()])

    punctuation_change = problem_workflow.GeneratedProblemStatement.model_validate(
        {
            "statement": "The team hired five support specialists, this month.",
            "evidence": ["The team hired five support specialists,"],
        }
    )
    with pytest.raises(llm_client.ValidationFailure, match="not present"):
        problem_workflow.validate_problem_statement_evidence(
            punctuation_change, [_verified_signal()]
        )

    paraphrase = problem_workflow.GeneratedProblemStatement.model_validate(
        {
            "statement": "The organization added five support specialists this month.",
            "evidence": ["The team hired five support specialists"],
        }
    )
    with pytest.raises(llm_client.ValidationFailure, match="must appear verbatim"):
        problem_workflow.validate_problem_statement_evidence(paraphrase, [_verified_signal()])


def test_problem_statement_schema_requires_one_or_two_sentences_and_four_word_spans():
    with pytest.raises(ValueError, match="one or two sentences"):
        problem_workflow.GeneratedProblemStatement.model_validate(
            {
                "statement": "First sentence. Second sentence. Third sentence.",
                "evidence": [EVIDENCE_SPAN],
            }
        )
    with pytest.raises(ValueError, match="between 4 and 15 words"):
        problem_workflow.GeneratedProblemStatement.model_validate(
            {"statement": "The team hired specialists.", "evidence": ["hired specialists"]}
        )


def test_no_verified_signal_skips_without_model_call_and_persists_reason(db_path, monkeypatch):
    product_id, prospect_id, profile_id, icp_id, _old_signal_run, _ids = _create_case(
        db_path, signals=[_verified_signal()]
    )
    conn = db.connect()
    try:
        # The newest successful run is empty, so older evidence is not reused.
        empty_run = db.create_signal_run(conn, prospect_id=prospect_id, model_name="empty-signals")
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
        lambda *args, **kwargs: pytest.fail("problem statements must skip without verified evidence"),
    )
    monkeypatch.setattr(
        llm_client,
        "resolve_model_name",
        lambda *_args: pytest.fail("model resolution is unnecessary without verified evidence"),
    )
    response = _post(_path(product_id, prospect_id))

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "skipped"
    assert result["statement"] is None
    assert result["evidence"] is None
    assert result["reason"] == "no verified evidence"
    assert result["business_profile_id"] == profile_id
    assert result["icp_id"] == icp_id
    assert result["signal_run_id"] == empty_run
    assert result["source_signal_ids"] == []
    assert _get(_path(product_id, prospect_id)).json() == result
    conn = db.connect()
    try:
        stored = db.get_problem_statement_run(conn, result["id"])
        assert stored["status"] == "skipped"
        assert stored["error"] == "no verified evidence"
        assert conn.execute("SELECT COUNT(*) FROM inference_log").fetchone()[0] == 0
    finally:
        conn.close()


def test_problem_statement_retries_invalid_evidence_then_persists_failure(db_path, monkeypatch):
    product_id, prospect_id, *_ = _create_case(db_path, signals=[_verified_signal()])
    outputs = [
        {
            "statement": "A fictional contract is being signed by the prospect.",
            "evidence": ["A fictional contract is being signed"],
        },
        {
            "statement": "A growing organization added new staff this month.",
            "evidence": [EVIDENCE_SPAN],
        },
        {"statement": STATEMENT, "evidence": ["hired five support"]},
    ]
    prompts = []
    options = []

    def handler(request):
        payload = json.loads(request.content)
        prompts.append(payload["messages"][-1]["content"])
        options.append(payload["options"])
        return _response(outputs[len(options) - 1])

    _use_mock_transport(monkeypatch, handler)
    response = _post(_path(product_id, prospect_id))

    assert response.status_code == 502
    result = response.json()
    assert result["status"] == "failed"
    assert result["statement"] is None
    assert result["evidence"] is None
    assert "InvalidJsonResponse" in result["error"]
    assert "evidence[0]" in result["error"]
    assert len(options) == 3
    assert [value["seed"] for value in options] == [42, 43, 44]
    assert [value["temperature"] for value in options] == [0.0, 0.2, 0.2]
    assert "previous answer was invalid" in prompts[1]
    assert "previous answer was invalid" in prompts[2]
    assert "must appear verbatim in the statement" in prompts[2]
    assert _get(_path(product_id, prospect_id)).json() == result

    conn = db.connect()
    try:
        row = db.get_problem_statement_run(conn, result["id"])
        assert row["status"] == "failed"
        assert row["statement"] == ""
        assert row["evidence_json"] is None
        assert row["seed"] == 44
        assert row["temperature"] == 0.2
    finally:
        conn.close()


def test_unavailable_ollama_queues_and_worker_replays_problem_statement(db_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "queued-problem-model")
    product_id, prospect_id, *_ = _create_case(db_path, signals=[_verified_signal()])

    def unavailable(request):
        raise httpx.ConnectError("mocked local outage", request=request)

    _use_mock_transport(monkeypatch, unavailable)
    queued_response = _post(_path(product_id, prospect_id))
    assert queued_response.status_code == 202
    queued = queued_response.json()
    assert queued["status"] == "queued"
    assert queued["queue_task_id"] is not None

    conn = db.connect()
    try:
        task = db.get_task(conn, queued["queue_task_id"])
        assert task["status"] == "queued"
        assert json.loads(task["payload_json"]) == {
            "problem_statement_id": queued["id"],
            "product_id": product_id,
            "prospect_id": prospect_id,
            "model_name": "queued-problem-model",
        }
    finally:
        conn.close()

    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    previous = HANDLERS.get(problem_workflow.TASK_TYPE)
    problem_workflow.register_problem_statement_handler()
    try:
        # An unavailable inference requeues the same task without consuming an attempt.
        assert QueueWorker().run_once() == 1
        conn = db.connect()
        try:
            retry_task = db.get_task(conn, queued["queue_task_id"])
            assert retry_task["status"] == "queued"
            assert retry_task["attempts"] == 0
            assert db.get_problem_statement_run(conn, queued["id"])["status"] == "queued"
        finally:
            conn.close()

        # Recovery uses the same persisted source IDs and completes that task.
        _use_mock_transport(
            monkeypatch,
            lambda _request: _response(
                {"statement": STATEMENT, "evidence": [EVIDENCE_SPAN]}
            ),
        )
        assert QueueWorker().run_once() == 1
    finally:
        if previous is None:
            HANDLERS.pop(problem_workflow.TASK_TYPE, None)
        else:
            HANDLERS[problem_workflow.TASK_TYPE] = previous

    completed = _get(_path(product_id, prospect_id)).json()
    assert completed["status"] == "succeeded"
    assert completed["statement"] == STATEMENT
    assert completed["queue_task_id"] == queued["queue_task_id"]
    conn = db.connect()
    try:
        assert db.get_task(conn, queued["queue_task_id"])["status"] == "done"
    finally:
        conn.close()
