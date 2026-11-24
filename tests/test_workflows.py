from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app import db, llm_client
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker
from app.workflows import icp, profile, register_workflow_handlers


PROFILE_BAKERY = {
    "summary": "Bakery: A neighborhood bakery sells seasonal pastries.",
    "value_proposition": "Offers made-to-order cakes for local events.",
    "key_features": ["seasonal menu", "pre-order pickup"],
    "pain_points_solved": ["seasonal menu planning"],
    "differentiators": ["not stated"],
    "typical_buyer": "bakery owner",
    "typical_team_size": "not stated",
    "working_situation": "Owners plan seasonal menus and may open a second retail storefront as the bakery grows.",
    "not_for": ["businesses without a retail shop"],
}
PROFILE_BAKERY_NO_NAME = {
    **PROFILE_BAKERY,
    "summary": "A neighborhood pastry shop sells seasonal pastries.",
}
PROFILE_PLANETARIUM = {
    "summary": "Planetarium: A planetarium runs public astronomy and science education programs.",
    "value_proposition": "Provides scheduled educational shows.",
    "key_features": ["show calendar", "visitor programs"],
    "pain_points_solved": ["coordinating public show schedules"],
    "differentiators": ["not stated"],
    "typical_buyer": "program director",
    "typical_team_size": "not stated",
    "working_situation": "Staff coordinate public astronomy programs and may replace the projector system before the winter season.",
    "not_for": ["organizations without public programming"],
}
PROFILE_PLANETARIUM_NO_NAME = {
    **PROFILE_PLANETARIUM,
    "summary": "A public venue runs astronomy and science education programs.",
}
BAKERY_DOC = (
    "SAMPLE profile facts for an unrelated bakery. A neighborhood bakery sells seasonal pastries "
    "and offers made-to-order cakes for local events. Its seasonal menu includes pre-order pickup. "
    "One stated pain point is seasonal menu planning. The typical buyer is a bakery owner. Owners "
    "plan seasonal menus and may open a second retail storefront as the bakery grows. It is not for "
    "businesses without a retail shop."
)
PLANETARIUM_DOC = (
    "SAMPLE PLANETARIUM-DOC-ONLY source. A planetarium runs public astronomy and science education "
    "programs and provides scheduled educational shows. Its features include a show calendar and "
    "visitor programs. One stated pain point is coordinating public show schedules. The typical buyer "
    "is a program director. Staff coordinate public astronomy programs and may replace the "
    "projector system before the winter season. It is not for organizations without public programming."
)
ICP_BAKERY = {
    "industries": ["neighborhood bakery"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["bakery owner"],
    "pain_points": ["seasonal menu planning"],
    "trigger_events": ["opening a second retail storefront"],
    "disqualifiers": ["businesses without a retail shop"],
}
ICP_PLANETARIUM = {
    "industries": ["science education"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["program director"],
    "pain_points": ["coordinating public show schedules"],
    "trigger_events": ["replacing the projector system before the winter season"],
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


def _post_raw(path: str) -> httpx.Response:
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path)

    return asyncio.run(request())


def _post(path: str) -> httpx.Response:
    response = _post_raw(path)
    if not path.endswith("/profile") or response.status_code != 202:
        return response

    # Workflow unit tests drive the same queued worker synchronously so each
    # test can inspect a terminal API result without waiting for a daemon thread.
    import app.queue_worker as queue_worker

    previous_probe = queue_worker.ollama_up
    register_workflow_handlers()
    queue_worker.ollama_up = lambda: True
    try:
        QueueWorker().run_once()
    finally:
        queue_worker.ollama_up = previous_probe
    run_id = response.json()["id"]
    final = _get(f"/api/workflow-runs/{run_id}").json()
    if final["status"] == "succeeded":
        return httpx.Response(200, json=final)
    if final["status"] == "failed":
        return httpx.Response(502, json=final)
    return httpx.Response(202, json=final)


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
    profile_prompt = profile.build_profile_prompt(long_document, "RelayCue")
    icp_prompt = icp.build_icp_prompt(long_document)
    assert "TRUNCATED-TAIL" not in profile_prompt
    assert "TRUNCATED-TAIL" not in icp_prompt
    assert profile_prompt.endswith("Company-info document:\n" + "D" * 3000)
    assert icp_prompt.endswith("Stored business profile:\n" + "D" * 3000)


def test_profile_api_uses_json_schema_cleans_reply_and_persists_model(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "sample-test-model")
    company_info = tmp_path / "profile.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Bakery", company_info)
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert request.url.path == "/api/chat"
        return _chat_response(f"```json\n{_profile_json(PROFILE_BAKERY_NO_NAME)}\n```")

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["result"] == PROFILE_BAKERY_NO_NAME
    assert "bakery" not in body["result"]["summary"].casefold()
    assert body["model_name"] == "sample-test-model"
    assert body["temperature"] == 0.0
    assert body["seed"] == 42
    assert body["created_at"] and body["updated_at"]
    assert len(seen) == 1
    prompt_payload = seen[0]
    assert prompt_payload["format"] == profile.BusinessProfile.model_json_schema()
    assert prompt_payload["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": profile.NUM_CTX,
    }
    prompt = prompt_payload["messages"][-1]["content"]
    expected_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert body["prompt_hash"] == expected_prompt_hash
    assert body["commit_hash"] == "unknown" or len(body["commit_hash"]) in {40, 64}
    assert "SAMPLE profile facts for an unrelated bakery." in prompt
    assert "Bakery:" not in prompt
    assert "not stated" in prompt

    conn = db.connect()
    try:
        saved = conn.execute(
            "SELECT product_id, profile_json, model_name, temperature, seed, repeat_penalty, "
            "prompt_hash, commit_hash, created_at FROM business_profiles"
        ).fetchone()
        assert saved["product_id"] == product_id
        assert json.loads(saved["profile_json"]) == PROFILE_BAKERY_NO_NAME
        assert saved["model_name"] == "sample-test-model"
        assert saved["temperature"] == 0.0
        assert saved["seed"] == 42
        assert saved["repeat_penalty"] == 1.0
        assert saved["prompt_hash"] == expected_prompt_hash
        assert saved["commit_hash"] == body["commit_hash"]
        inference = conn.execute("SELECT * FROM inference_log ORDER BY id DESC LIMIT 1").fetchone()
        assert inference["prompt_hash"] == expected_prompt_hash
        assert inference["commit_hash"] == body["commit_hash"]
        assert saved["created_at"]
    finally:
        conn.close()

    get_response = _get(f"/api/products/{product_id}/profile")
    assert get_response.status_code == 200
    assert get_response.json() == body


def test_profile_post_returns_pollable_run_then_worker_completes_with_mocked_ollama(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "pollable-profile-model")
    company_info = tmp_path / "pollable-profile.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Pollable profile", company_info)
    _use_mock_transport(
        monkeypatch,
        lambda request: _chat_response(_profile_json(PROFILE_BAKERY_NO_NAME)),
    )

    response = _post_raw(f"/api/products/{product_id}/profile")
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["result"] is None
    assert _get(f"/api/workflow-runs/{queued['id']}").json() == queued

    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    register_workflow_handlers()
    assert QueueWorker().run_once() == 1
    completed = _get(f"/api/workflow-runs/{queued['id']}").json()
    assert completed["status"] == "succeeded"
    assert completed["result"] == PROFILE_BAKERY_NO_NAME
    assert completed["model_name"] == "pollable-profile-model"


def test_profile_accepts_grounded_summary_with_a_legitimate_colon(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "profile-colon-model")
    company_info = tmp_path / "colon-summary.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Bakery", company_info)
    colon_profile = dict(PROFILE_BAKERY_NO_NAME)
    colon_profile["summary"] = "A neighborhood pastry shop: sells seasonal pastries."

    _use_mock_transport(
        monkeypatch, lambda _request: _chat_response(_profile_json(colon_profile))
    )
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 200
    assert response.json()["result"]["summary"] == colon_profile["summary"]


def test_profile_grounding_failure_retries_with_feedback_before_persisting(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "profile-grounding-model")
    company_info = tmp_path / "grounded.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Bakery", company_info)
    hallucinated = dict(PROFILE_BAKERY_NO_NAME)
    hallucinated["summary"] = "A nationwide cloud accounting platform guarantees savings."
    replies = iter([_profile_json(hallucinated), _profile_json(PROFILE_BAKERY_NO_NAME)])
    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return _chat_response(next(replies))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 200
    assert response.json()["result"] == PROFILE_BAKERY_NO_NAME
    assert len(prompts) == 2
    assert "Your previous answer was invalid:" in prompts[1]
    assert "profile grounding failed" in prompts[1]
    conn = db.connect()
    try:
        saved = conn.execute("SELECT profile_json FROM business_profiles").fetchone()
        assert json.loads(saved["profile_json"]) == PROFILE_BAKERY_NO_NAME
        statuses = [row["status"] for row in conn.execute("SELECT status FROM inference_log ORDER BY id")]
        assert statuses == ["error:invalid_json", "ok"]
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("summary", "expected_check", "offending_text"),
    [
        (
            "RelayC: A browser-based workspace...",
            "case-insensitive prefix of at least four characters",
            "RelayC:",
        ),
        (
            "RelayCue is a browser-based workspace.",
            "must not contain the product name",
            "RelayCue",
        ),
    ],
)
def test_profile_rejects_product_name_or_near_variant_on_all_retries(
    db_path, monkeypatch, tmp_path, summary, expected_check, offending_text
):
    monkeypatch.setenv("DEFAULT_MODEL", "product-name-check-model")
    company_info = tmp_path / "relaycue.md"
    company_info.write_text("RelayCue is a browser-based workspace.", encoding="utf-8")
    product_id = _create_product("RelayCue", company_info)
    invalid_profile = {
        "summary": summary,
        "value_proposition": "not stated",
        "key_features": ["not stated"],
        "pain_points_solved": ["not stated"],
        "differentiators": ["not stated"],
        "typical_buyer": "not stated",
        "typical_team_size": "not stated",
        "working_situation": "not stated",
        "not_for": ["not stated"],
    }
    prompts = []
    options_sent = []
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        prompts.append(payload["messages"][-1]["content"])
        options_sent.append(payload["options"])
        return _chat_response(_profile_json(invalid_profile))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 502
    assert calls == 3
    assert [options["seed"] for options in options_sent] == [42, 43, 44]
    assert [options["temperature"] for options in options_sent] == [0.0, 0.2, 0.2]
    assert all(options["repeat_penalty"] == 1.0 for options in options_sent)
    assert "without using the product name" in prompts[0]
    assert "must not contain the product name" in prompts[1]
    body = response.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert "InvalidJsonResponse" in body["error"]
    assert expected_check in body["error"]
    assert f'value="{offending_text}"' in body["error"]
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM business_profiles").fetchone()[0] == 0
        run = conn.execute(
            "SELECT status, result_json, error, temperature, seed, repeat_penalty FROM workflow_runs"
        ).fetchone()
        assert run["status"] == "failed"
        assert run["result_json"] is None
        assert expected_check in run["error"]
        assert f'value="{offending_text}"' in run["error"]
        assert run["temperature"] == 0.0
        assert run["seed"] == 42
        assert run["repeat_penalty"] == 1.0
        attempt_options = conn.execute(
            "SELECT temperature, seed, repeat_penalty FROM inference_log ORDER BY id"
        ).fetchall()
        assert [tuple(row) for row in attempt_options] == [
            (0.0, 42, 1.0),
            (0.2, 43, 1.0),
            (0.2, 44, 1.0),
        ]
    finally:
        conn.close()


def test_profile_rejects_ungrounded_stray_token_and_persists_failure(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "profile-stray-token-model")
    company_info = tmp_path / "stray-token.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Bakery", company_info)
    invalid_profile = dict(PROFILE_BAKERY_NO_NAME)
    invalid_profile["key_features"] = ["B2: B2B software", "pre-order pickup"]
    options_sent = []
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        options_sent.append(payload["options"])
        return _chat_response(_profile_json(invalid_profile))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 502
    assert calls == 3
    assert [options["seed"] for options in options_sent] == [42, 43, 44]
    assert [options["temperature"] for options in options_sent] == [0.0, 0.2, 0.2]
    body = response.json()
    assert body["status"] == "failed"
    assert "key_features[0]" in body["error"]
    assert "repeated-token artifact" in body["error"]
    assert 'value="B2: B2"' in body["error"]
    conn = db.connect()
    try:
        run = conn.execute("SELECT status, error FROM workflow_runs").fetchone()
        assert run["status"] == "failed"
        assert "key_features[0]" in run["error"]
        assert 'value="B2: B2"' in run["error"]
        attempts = conn.execute(
            "SELECT temperature, seed, repeat_penalty FROM inference_log ORDER BY id"
        ).fetchall()
        assert [tuple(row) for row in attempts] == [
            (0.0, 42, 1.0),
            (0.2, 43, 1.0),
            (0.2, 44, 1.0),
        ]
    finally:
        conn.close()


def test_workflow_retries_invalid_json_and_validates_before_saving(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "retry-test-model")
    company_info = tmp_path / "retry.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Bakery", company_info)
    prompts = []
    replies = iter(
        ["not json", json.dumps({"summary": "required fields are missing"}), _profile_json(PROFILE_BAKERY_NO_NAME)]
    )

    def handler(request):
        payload = json.loads(request.content)
        prompts.append(payload["messages"][-1]["content"])
        return _chat_response(next(replies))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/profile")

    assert response.status_code == 200
    assert response.json()["result"] == PROFILE_BAKERY_NO_NAME
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
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("Bakery", company_info)

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
        return _chat_response(_profile_json(PROFILE_BAKERY_NO_NAME))

    _use_mock_transport(monkeypatch, healthy)
    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    previous_profile = HANDLERS.get(profile.TASK_TYPE)
    previous_icp = HANDLERS.get(icp.TASK_TYPE)
    previous_draft = HANDLERS.get("workflow.draft")
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
        if previous_draft is None:
            HANDLERS.pop("workflow.draft", None)
        else:
            HANDLERS["workflow.draft"] = previous_draft

    completed = _get(f"/api/products/{product_id}/profile").json()
    assert completed["status"] == "succeeded"
    assert completed["result"] == PROFILE_BAKERY_NO_NAME
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
    bakery_doc.write_text(
        BAKERY_DOC.replace("SAMPLE profile facts for an unrelated bakery.", "SAMPLE BAKERY-DOC-ONLY source."),
        encoding="utf-8",
    )
    planetarium_doc.write_text(PLANETARIUM_DOC, encoding="utf-8")
    bakery_id = _create_product("Bakery", bakery_doc)
    planetarium_id = _create_product("Planetarium", planetarium_doc)

    def handler(request):
        payload = json.loads(request.content)
        assert payload["options"]["temperature"] == 0.0
        assert payload["options"]["seed"] == 42
        prompt = payload["messages"][-1]["content"]
        if "Create a business profile" in prompt:
            if "BAKERY-DOC-ONLY" in prompt:
                return _chat_response(_profile_json(PROFILE_BAKERY_NO_NAME))
            assert "PLANETARIUM-DOC-ONLY" in prompt
            return _chat_response(_profile_json(PROFILE_PLANETARIUM_NO_NAME))
        if "Create an ideal-customer profile" in prompt:
            assert "BAKERY-DOC-ONLY" not in prompt
            assert "PLANETARIUM-DOC-ONLY" not in prompt
            if "bakery owner" in prompt:
                return _chat_response(json.dumps(ICP_BAKERY))
            assert "program director" in prompt
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


def test_icp_grounding_failure_retries_once_and_uses_profile_fields(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "icp-grounding-model")
    company_info = tmp_path / "icp.md"
    company_info.write_text(BAKERY_DOC, encoding="utf-8")
    product_id = _create_product("ICP grounding", company_info)
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(PROFILE_BAKERY), "profile-model", db.utcnow()),
        )
        conn.commit()
    finally:
        conn.close()

    hallucinated = dict(ICP_BAKERY)
    hallucinated["trigger_events"] = ["seasonal menu"]
    prompts = []
    replies = iter([json.dumps(hallucinated), json.dumps(ICP_BAKERY)])

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return _chat_response(next(replies))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/icp")

    assert response.status_code == 200
    assert response.json()["result"] == ICP_BAKERY
    assert len(prompts) == 2
    assert "typical_buyer" in prompts[0]
    assert "typical_team_size" in prompts[0]
    assert "working_situation" in prompts[0]
    assert "not_for" in prompts[0]
    assert (
        'trigger_events: if the profile does not describe an event, return ["not stated"]; '
        "never invent one."
    ) in prompts[0]
    assert (
        "disqualifiers: copy only not_for items verbatim; never write a condition about lacking "
        "the product."
    ) in prompts[0]
    assert (
        "pain_points: use the profile's pain_points_solved and working_situation wording; "
        "do not add a new pain."
    ) in prompts[0]
    assert "fictional bookstore" in prompts[0]
    assert "RelayCue" not in prompts[0] and "FieldNest" not in prompts[0]
    assert "Your previous answer was invalid:" in prompts[1]
    assert "restates the product or its features" in prompts[1]


def test_icp_grounding_failure_stores_field_check_and_value(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "icp-specific-failure-model")
    product_id = _create_product("ICP diagnostic", tmp_path / "unused.md")
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(PROFILE_BAKERY), "profile-model", db.utcnow()),
        )
        conn.commit()
    finally:
        conn.close()

    invalid_icp = dict(ICP_BAKERY)
    invalid_icp["trigger_events"] = ["seasonal menu"]

    def handler(_request):
        return _chat_response(json.dumps(invalid_icp))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/icp")

    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert "InvalidJsonResponse" in body["error"]
    assert "trigger_events[0]" in body["error"]
    assert "restates the product or its features" in body["error"]
    assert 'value="seasonal menu"' in body["error"]
    conn = db.connect()
    try:
        run = conn.execute("SELECT status, error FROM workflow_runs").fetchone()
        assert run["status"] == "failed"
        assert "trigger_events[0]" in run["error"]
        assert 'value="seasonal menu"' in run["error"]
    finally:
        conn.close()


def test_icp_rejects_ungrounded_stray_token_and_retries_with_changed_seed(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "icp-stray-token-model")
    product_id = _create_product("ICP stray token", tmp_path / "unused.md")
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(PROFILE_BAKERY), "profile-model", db.utcnow()),
        )
        conn.commit()
    finally:
        conn.close()

    invalid_icp = dict(ICP_BAKERY)
    invalid_icp["industries"] = ["B2: B2B software"]
    options_sent = []

    def handler(request):
        options_sent.append(json.loads(request.content)["options"])
        return _chat_response(json.dumps(invalid_icp))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/products/{product_id}/icp")

    assert response.status_code == 502
    assert [options["seed"] for options in options_sent] == [42, 43, 44]
    assert [options["temperature"] for options in options_sent] == [0.0, 0.2, 0.2]
    body = response.json()
    assert "industries[0]" in body["error"]
    assert "repeated-token artifact" in body["error"]
    assert 'value="B2: B2"' in body["error"]
    conn = db.connect()
    try:
        run = conn.execute("SELECT status, error FROM workflow_runs").fetchone()
        assert run["status"] == "failed"
        assert "industries[0]" in run["error"]
        assert 'value="B2: B2"' in run["error"]
    finally:
        conn.close()


def test_icp_accepts_a_grounded_string_with_a_legitimate_colon(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "icp-colon-model")
    product_id = _create_product("ICP colon", tmp_path / "unused.md")
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(PROFILE_BAKERY), "profile-model", db.utcnow()),
        )
        conn.commit()
    finally:
        conn.close()

    valid_icp = dict(ICP_BAKERY)
    valid_icp["industries"] = ["Bakery: neighborhood retail"]
    _use_mock_transport(
        monkeypatch, lambda _request: _chat_response(json.dumps(valid_icp))
    )
    response = _post(f"/api/products/{product_id}/icp")

    assert response.status_code == 200
    assert response.json()["result"]["industries"] == ["Bakery: neighborhood retail"]


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


def test_legacy_profile_remains_readable_and_is_not_rewritten(db_path, tmp_path):
    legacy = {
        "summary": "A neighborhood bakery sells seasonal pastries.",
        "value_proposition": "Offers made-to-order cakes for local events.",
        "key_features": [],
        "pain_points_solved": [],
        "differentiators": ["not stated"],
    }
    product_id = _create_product("Legacy profile", tmp_path / "unused.md")
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO business_profiles (product_id, profile_json, model_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (product_id, json.dumps(legacy), "old-model", db.utcnow()),
        )
        conn.commit()
    finally:
        conn.close()

    stored = icp._stored_profile(product_id)
    assert stored.typical_buyer == "not stated"
    assert stored.typical_team_size == "not stated"
    assert stored.working_situation == "not stated"
    assert stored.not_for == ["not stated"]
    assert stored.key_features == ["not stated"]
    conn = db.connect()
    try:
        persisted = json.loads(db.latest_business_profile(conn, product_id)["profile_json"])
        assert persisted == legacy
    finally:
        conn.close()


def test_stray_token_text_is_allowed_when_the_exact_match_is_in_its_source():
    source_phrase = "B2: B2B software"
    profile_data = dict(PROFILE_BAKERY_NO_NAME)
    profile_data["key_features"] = [source_phrase, "pre-order pickup"]
    profile.validate_profile_grounding(
        profile.BusinessProfile.model_validate(profile_data),
        f"{BAKERY_DOC}\n{source_phrase}",
        "Bakery",
    )

    icp_profile_data = dict(PROFILE_BAKERY)
    icp_profile_data["value_proposition"] = source_phrase
    grounded_icp = dict(ICP_BAKERY)
    grounded_icp["industries"] = [source_phrase]
    icp.validate_icp_grounding(
        icp.IdealCustomerProfile.model_validate(grounded_icp),
        profile.BusinessProfile.model_validate(icp_profile_data),
    )


def test_icp_grounding_allows_unsupported_fields_but_rejects_product_restatement():
    stored_profile = profile.BusinessProfile.model_validate(PROFILE_BAKERY)
    valid_icp = icp.IdealCustomerProfile.model_validate(ICP_BAKERY)
    icp.validate_icp_grounding(valid_icp, stored_profile)

    unsupported_profile = stored_profile.model_copy(
        update={
            "typical_buyer": "not stated",
            "typical_team_size": "not stated",
            "pain_points_solved": ["not stated"],
            "working_situation": "not stated",
            "not_for": ["not stated"],
        }
    )
    sparse_icp = icp.IdealCustomerProfile.model_validate(
        {
            "industries": ["not stated"],
            "company_size": {"min": None, "max": None},
            "buyer_titles": [],
            "pain_points": [],
            "trigger_events": [],
            "disqualifiers": [],
        }
    )
    icp.validate_icp_grounding(sparse_icp, unsupported_profile)

    product_restatement = dict(ICP_BAKERY)
    product_restatement["trigger_events"] = ["seasonal menu"]
    with pytest.raises(ValueError, match="trigger_events"):
        icp.validate_icp_grounding(
            icp.IdealCustomerProfile.model_validate(product_restatement), stored_profile
        )

    product_disqualifier = dict(ICP_BAKERY)
    product_disqualifier["disqualifiers"] = ["teams that use seasonal menu pickup"]
    with pytest.raises(ValueError, match="disqualifiers"):
        icp.validate_icp_grounding(
            icp.IdealCustomerProfile.model_validate(product_disqualifier), stored_profile
        )
