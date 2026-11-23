from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from app import db, llm_client
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker
from app.workflows import icp, profile, register_workflow_handlers


PROFILE_BAKERY = {
    "summary": "A neighborhood bakery sells seasonal pastries.",
    "value_proposition": "Offers made-to-order cakes for local events.",
    "key_features": ["seasonal menu", "pre-order pickup"],
    "pain_points_solved": ["not stated"],
    "differentiators": ["not stated"],
}
PROFILE_PLANETARIUM = {
    "summary": "A planetarium runs public astronomy programs.",
    "value_proposition": "Provides scheduled educational shows.",
    "key_features": ["show calendar", "visitor programs"],
    "pain_points_solved": ["not stated"],
    "differentiators": ["not stated"],
}
ICP_BAKERY = {
    "industries": ["independent bakeries"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["bakery owner"],
    "pain_points": ["seasonal menu planning"],
    "trigger_events": ["opening a storefront"],
    "disqualifiers": ["businesses without a retail shop"],
}
ICP_PLANETARIUM = {
    "industries": ["science education"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["program director"],
    "pain_points": ["coordinating public show schedules"],
    "trigger_events": ["adding a new public program"],
    "disqualifiers": ["organizations without public programming"],
}


def _create_product(name: str, docs_path: Path) -> int:
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name=name, docs_path=str(docs_path))
        conn.commit()
        return product_id
    finally:
        conn.close()


def _use_mock_transport(monkeypatch, handler) -> None:
    def factory(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_client, "_client", factory)


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


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {"content": content},
            "prompt_eval_count": 80,
            "eval_count": 15,
            "total_duration": 50_000_000,
        },
    )


def _profile_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


def test_prompt_inputs_are_trimmed_to_3000_characters():
    long_document = "D" * 3000 + "TRUNCATED-TAIL"
    profile_prompt = profile.build_profile_prompt(long_document)
    icp_prompt = icp.build_icp_prompt(long_document)
    assert "TRUNCATED-TAIL" not in profile_prompt
    assert "TRUNCATED-TAIL" not in icp_prompt
    assert profile_prompt.endswith("Company-info document:\n" + "D" * 3000)
    assert icp_prompt.endswith("Stored business profile:\n" + "D" * 3000)


def test_profile_api_uses_json_schema_cleans_reply_and_persists_model(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "sample-test-model")
    company_info = tmp_path / "profile.md"
    company_info.write_text("SAMPLE profile facts for an unrelated bakery.", encoding="utf-8")
    product_id = _create_product("Product name must not enter the prompt", company_info)
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert request.url.path == "/api/chat"
        return _chat_response(f"```json\n{_profile_json(PROFILE_BAKERY)}\n```")

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["result"] == PROFILE_BAKERY
    assert body["model_name"] == "sample-test-model"
    assert body["created_at"] and body["updated_at"]
    assert len(seen) == 1
    prompt_payload = seen[0]
    assert prompt_payload["format"] == profile.BusinessProfile.model_json_schema()
    assert prompt_payload["options"]["num_ctx"] == profile.NUM_CTX
    prompt = prompt_payload["messages"][-1]["content"]
    assert "SAMPLE profile facts for an unrelated bakery." in prompt
    assert "Product name must not enter the prompt" not in prompt
    assert "not stated" in prompt

    conn = db.connect()
    try:
        saved = conn.execute(
            "SELECT product_id, profile_json, model_name, created_at FROM business_profiles"
        ).fetchone()
        assert saved["product_id"] == product_id
        assert json.loads(saved["profile_json"]) == PROFILE_BAKERY
        assert saved["model_name"] == "sample-test-model"
        assert saved["created_at"]
    finally:
        conn.close()

    get_response = _get(f"/api/products/{product_id}/profile")
    assert get_response.status_code == 200
    assert get_response.json() == body


def test_workflow_retries_invalid_json_and_validates_before_saving(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "retry-test-model")
    company_info = tmp_path / "retry.md"
    company_info.write_text("SAMPLE company information.", encoding="utf-8")
    product_id = _create_product("Retry product", company_info)
    prompts = []
    replies = iter(
        ["not json", json.dumps({"summary": "required fields are missing"}), _profile_json(PROFILE_BAKERY)]
    )

    def handler(request):
        payload = json.loads(request.content)
        prompts.append(payload["messages"][-1]["content"])
        return _chat_response(next(replies))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 200
    assert response.json()["result"] == PROFILE_BAKERY
    assert len(prompts) == 3
    assert "Your previous answer was invalid:" in prompts[1]
    assert "matching the schema" in prompts[1]
    assert "Your previous answer was invalid:" in prompts[2]
    conn = db.connect()
    try:
        rows = conn.execute("SELECT status FROM inference_log ORDER BY id").fetchall()
        assert [row["status"] for row in rows] == [
            "error:invalid_json", "error:invalid_json", "ok"
        ]
        assert conn.execute("SELECT COUNT(*) FROM business_profiles").fetchone()[0] == 1
    finally:
        conn.close()


def test_unavailable_ollama_queues_and_worker_replays_profile(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "queued-test-model")
    company_info = tmp_path / "queued.md"
    company_info.write_text("SAMPLE queued-workflow source.", encoding="utf-8")
    product_id = _create_product("Queued product", company_info)

    def unavailable(request):
        raise httpx.ConnectError("Ollama is stopped", request=request)

    _use_mock_transport(monkeypatch, unavailable)
    queued_response = _post(f"/api/products/{product_id}/profile")
    assert queued_response.status_code == 202
    queued = queued_response.json()
    assert queued["status"] == "queued"
    assert queued["result"] is None
    assert "OllamaUnavailable" in queued["error"]
    assert queued["queue_task_id"] is not None

    conn = db.connect()
    try:
        task = db.get_task(conn, queued["queue_task_id"])
        payload = json.loads(task["payload_json"])
        assert task["status"] == "queued"
        assert payload == {
            "product_id": product_id,
            "workflow_run_id": queued["id"],
            "model_name": "queued-test-model",
        }
    finally:
        conn.close()

    def healthy(request):
        assert request.url.path == "/api/chat"
        return _chat_response(_profile_json(PROFILE_BAKERY))

    _use_mock_transport(monkeypatch, healthy)
    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    previous_profile = HANDLERS.get(profile.TASK_TYPE)
    previous_icp = HANDLERS.get(icp.TASK_TYPE)
    register_workflow_handlers()
    try:
        assert QueueWorker().run_once() == 1
    finally:
        if previous_profile is None:
            HANDLERS.pop(profile.TASK_TYPE, None)
        else:
            HANDLERS[profile.TASK_TYPE] = previous_profile
        if previous_icp is None:
            HANDLERS.pop(icp.TASK_TYPE, None)
        else:
            HANDLERS[icp.TASK_TYPE] = previous_icp

    completed = _get(f"/api/products/{product_id}/profile").json()
    assert completed["status"] == "succeeded"
    assert completed["result"] == PROFILE_BAKERY
    conn = db.connect()
    try:
        task = db.get_task(conn, queued["queue_task_id"])
        assert task["status"] == "done"
    finally:
        conn.close()


def test_profile_and_icp_are_separated_by_product_and_icp_reads_stored_profile_only(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "separation-test-model")
    bakery_doc = tmp_path / "bakery.md"
    planetarium_doc = tmp_path / "planetarium.md"
    bakery_doc.write_text("SAMPLE BAKERY-DOC-ONLY source.", encoding="utf-8")
    planetarium_doc.write_text("SAMPLE PLANETARIUM-DOC-ONLY source.", encoding="utf-8")
    bakery_id = _create_product("Bakery", bakery_doc)
    planetarium_id = _create_product("Planetarium", planetarium_doc)

    def handler(request):
        prompt = json.loads(request.content)["messages"][-1]["content"]
        if "Create a business profile" in prompt:
            if "BAKERY-DOC-ONLY" in prompt:
                return _chat_response(_profile_json(PROFILE_BAKERY))
            assert "PLANETARIUM-DOC-ONLY" in prompt
            return _chat_response(_profile_json(PROFILE_PLANETARIUM))
        if "Create an ideal-customer profile" in prompt:
            assert "BAKERY-DOC-ONLY" not in prompt
            assert "PLANETARIUM-DOC-ONLY" not in prompt
            if "neighborhood bakery" in prompt:
                return _chat_response(json.dumps(ICP_BAKERY))
            assert "planetarium runs public astronomy programs" in prompt
            return _chat_response(json.dumps(ICP_PLANETARIUM))
        raise AssertionError("unexpected workflow prompt")

    _use_mock_transport(monkeypatch, handler)
    for product_id in (bakery_id, planetarium_id):
        profile_response = _post(f"/api/products/{product_id}/profile")
        assert profile_response.status_code == 200
    bakery_icp_response = _post(f"/api/products/{bakery_id}/icp")
    planetarium_icp_response = _post(f"/api/products/{planetarium_id}/icp")
    assert bakery_icp_response.status_code == planetarium_icp_response.status_code == 200
    bakery_icp = bakery_icp_response.json()
    planetarium_icp = planetarium_icp_response.json()
    assert bakery_icp["product_id"] == bakery_id
    assert planetarium_icp["product_id"] == planetarium_id
    assert bakery_icp["result"] == ICP_BAKERY
    assert planetarium_icp["result"] == ICP_PLANETARIUM
    assert bakery_icp["result"] != planetarium_icp["result"]
    assert _get(f"/api/products/{bakery_id}/icp").json() == bakery_icp
    assert _get(f"/api/products/{planetarium_id}/icp").json() == planetarium_icp

    conn = db.connect()
    try:
        stored = conn.execute(
            "SELECT product_id, icp_json, model_name FROM icps ORDER BY product_id"
        ).fetchall()
        assert [row["product_id"] for row in stored] == [bakery_id, planetarium_id]
        assert json.loads(stored[0]["icp_json"]) == ICP_BAKERY
        assert json.loads(stored[1]["icp_json"]) == ICP_PLANETARIUM
        assert all(row["model_name"] == "separation-test-model" for row in stored)
    finally:
        conn.close()


def test_invalid_generation_is_stored_and_returned_without_default_output(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "failure-test-model")
    company_info = tmp_path / "failure.md"
    company_info.write_text("SAMPLE failure-case source.", encoding="utf-8")
    product_id = _create_product("Failure product", company_info)
    calls = 0

    def invalid(request):
        nonlocal calls
        calls += 1
        return _chat_response("not valid JSON")

    _use_mock_transport(monkeypatch, invalid)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert "InvalidJsonResponse" in body["error"]
    assert body["model_name"] == "failure-test-model"
    assert calls == 3

    get_response = _get(f"/api/products/{product_id}/profile")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "failed"
    assert get_response.json()["result"] is None
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM business_profiles").fetchone()[0] == 0
        row = conn.execute("SELECT status, result_json, error FROM workflow_runs").fetchone()
        assert row["status"] == "failed"
        assert row["result_json"] is None
        assert "InvalidJsonResponse" in row["error"]
    finally:
        conn.close()


def test_icp_without_a_stored_profile_persists_failure_without_generating_output(
    db_path, monkeypatch, tmp_path
):
    company_info = tmp_path / "unused-source.md"
    company_info.write_text("SAMPLE this file must not be used for ICP.", encoding="utf-8")
    product_id = _create_product("ICP requires stored profile", company_info)

    def forbidden_request(request):
        raise AssertionError("ICP must not read the source file or call Ollama without a stored profile")

    _use_mock_transport(monkeypatch, forbidden_request)
    response = _post(f"/api/products/{product_id}/icp")

    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert "no stored business profile" in body["error"]
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM icps").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM business_profiles").fetchone()[0] == 0
        row = conn.execute("SELECT status, result_json, error FROM workflow_runs").fetchone()
        assert row["status"] == "failed"
        assert row["result_json"] is None
        assert "no stored business profile" in row["error"]
    finally:
        conn.close()
