from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app import db, llm_client, prospects
from app.main import app
from app.queue_worker import HANDLERS, QueueWorker
from app.workflows import signals as signal_workflow


def _new_prospect(db_path, monkeypatch, tmp_path, page_text: str) -> tuple[int, int]:
    page_dir = tmp_path / "prospect-pages"
    monkeypatch.setattr(prospects, "DEFAULT_PAGE_DIR", page_dir)
    conn = db.connect()
    try:
        product_number = int(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]) + 1
        product_id = db.create_product(conn, name=f"Signal unit test product {product_number}")
        prospect_id = db.create_prospect(
            conn,
            product_id=product_id,
            company_name="Private company metadata",
            company_domain="private.example",
        )
        conn.commit()
        prospects.store_prospect_page(
            conn, prospect_id=prospect_id, text=page_text, page_dir=page_dir
        )
        return product_id, prospect_id
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


def _model_output(items: list[dict]) -> str:
    return json.dumps({"signals": items}, ensure_ascii=False)


def test_empty_signal_list_is_valid_and_schema_fields_are_ordered():
    assert signal_workflow.SignalExtraction.model_validate({"signals": []}).signals == []
    assert list(signal_workflow.ProspectSignal.model_fields) == [
        "evidence",
        "type",
        "about_company",
    ]
    schema = signal_workflow.SignalExtraction.model_json_schema()
    assert "none" not in schema["$defs"]["ProspectSignal"]["properties"]["type"]["enum"]
    with pytest.raises(ValueError):
        signal_workflow.ProspectSignal.model_validate(
            {"evidence": "", "type": "none", "about_company": False}
        )


def test_legacy_stored_none_signal_still_loads(db_path):
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="legacy product")
        prospect_id = db.create_prospect(
            conn, product_id=product_id, company_name="Legacy Library"
        )
        run_id = db.create_signal_run(conn, prospect_id=prospect_id, model_name="old-model")
        legacy = [{"type": "none", "evidence": "", "about_company": False}]
        conn.execute(
            "UPDATE signal_runs SET status = 'succeeded', signals_json = ? WHERE id = ?",
            (json.dumps(legacy), run_id),
        )
        conn.commit()
        payload = signal_workflow.signal_run_payload(db.get_signal_run(conn, run_id))
    finally:
        conn.close()
    assert payload["signals"] == legacy


def test_page_text_delimiters_avoid_existing_marker_strings():
    page_text = (
        "Intro <<<PROSPECT_PAGE_TEXT_START_0>>> and "
        "<<<PROSPECT_PAGE_TEXT_END_0>>> footer"
    )
    prompt = signal_workflow.build_signal_prompt(page_text)
    assert "<<<PROSPECT_PAGE_TEXT_START_1>>>" in prompt
    assert "<<<PROSPECT_PAGE_TEXT_END_1>>>" in prompt
    assert page_text in prompt


def test_signal_api_validates_schema_uses_only_clean_page_and_persists_exact_removals(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-test-model")
    source = (
        "Navigation: Home | About | Careers\n"
        "Cookie Banner: We use cookies to personalize this site.\n"
        "Northwind Press opened a second neighborhood bookstore this month.\n"
        "Footer:\n"
        "Privacy policy\n"
        "Copyright 2026 Example Group.\n"
    )
    product_id, prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, source)
    seen_payloads = []
    quote = "Northwind Press opened a second neighborhood bookstore this month."

    def handler(request):
        payload = json.loads(request.content)
        seen_payloads.append(payload)
        assert request.url.path == "/api/chat"
        return _chat_response(
            "```json\n"
            + _model_output(
                [{"type": "expansion", "evidence": quote, "about_company": True}]
            )
            + "\n```"
        )

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["model_name"] == "signal-test-model"
    assert body["temperature"] == 0.0
    assert body["seed"] == 42
    assert body["repeat_penalty"] == 1.0
    assert body["quote_retries"] == 0
    assert body["prospect_id"] == prospect_id
    assert body["product_id"] == product_id
    assert body["signals"] == [
        {"type": "expansion", "evidence": quote, "about_company": True}
    ]
    assert body["drop_counts"] == {
        "quote": 0,
        "type": 0,
        "other_company": 0,
        "negated": 0,
        "stale": 0,
    }
    removed_lines = body["removed_content"]["lines"]
    assert [(item["reason"], item["text"]) for item in removed_lines] == [
        ("navigation", "Navigation: Home | About | Careers\n"),
        ("cookie_banner", "Cookie Banner: We use cookies to personalize this site.\n"),
        ("footer", "Footer:\n"),
        ("footer", "Privacy policy\n"),
        ("footer", "Copyright 2026 Example Group.\n"),
    ]
    assert body["removed_content"]["truncation"] is None
    assert body["removed_content"]["source_characters"] == len(source)
    assert body["removed_content"]["submitted_characters"] == len(quote) + 1
    assert body["created_at"] and body["updated_at"]

    assert len(seen_payloads) == 1
    payload = seen_payloads[0]
    assert payload["format"] == signal_workflow.SignalExtraction.model_json_schema()
    assert payload["options"] == {
        "temperature": 0.0,
        "seed": 42,
        "repeat_penalty": 1.0,
        "num_ctx": signal_workflow.NUM_CTX,
    }
    prompt = payload["messages"][-1]["content"]
    assert quote in prompt
    assert "Navigation: Home" not in prompt
    assert "Cookie Banner" not in prompt
    assert "Footer:" not in prompt
    assert "Private product metadata" not in prompt
    assert "Private company metadata" not in prompt
    assert "complete sentence copied exactly" in prompt
    assert "more than one year" in prompt
    assert "<<<PROSPECT_PAGE_TEXT_START_0>>>" in prompt
    assert prompt.index("<<<PROSPECT_PAGE_TEXT_START_0>>>") < prompt.index("Rules:")
    assert prompt.rstrip().endswith("and about_company.")

    assert _get(f"/api/prospects/{prospect_id}/signals").json() == body
    conn = db.connect()
    try:
        run = db.get_signal_run(conn, body["id"])
        assert run["status"] == "succeeded"
        assert run["product_id"] == product_id
        assert run["prospect_id"] == prospect_id
        assert run["model_name"] == "signal-test-model"
        assert run["temperature"] == 0.0
        assert run["seed"] == 42
        assert run["created_at"]
        assert json.loads(run["signals_json"]) == body["signals"]
        stored = conn.execute(
            "SELECT prospect_id, signal_run_id, type, evidence FROM signals"
        ).fetchall()
        assert [tuple(row) for row in stored] == [
            (prospect_id, body["id"], "expansion", quote)
        ]
    finally:
        conn.close()


def test_signal_schema_failures_retry_twice_and_then_succeed(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-retry-model")
    _, prospect_id = _new_prospect(
        db_path,
        monkeypatch,
        tmp_path,
        "The observatory installed a new infrared telescope this spring.",
    )
    contents = iter(
        [
            "not json",
            json.dumps(
                {
                    "signals": [
                        {
                            "type": "tech_change",
                            "evidence": "The observatory installed a new infrared telescope this spring.",
                        }
                    ]
                }
            ),
            _model_output(
                [
                    {
                        "type": "tech_change",
                        "evidence": "The observatory installed a new infrared telescope this spring.",
                        "about_company": True,
                    }
                ]
            ),
        ]
    )
    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][-1]["content"])
        return _chat_response(next(contents))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    assert response.json()["signals"][0]["type"] == "tech_change"
    assert len(prompts) == 3
    assert "Your previous answer was invalid:" in prompts[1]
    assert "Your previous answer was invalid:" in prompts[2]
    conn = db.connect()
    try:
        statuses = [
            row[0]
            for row in conn.execute("SELECT status FROM inference_log ORDER BY id").fetchall()
        ]
        assert statuses == ["error:invalid_json", "error:invalid_json", "ok"]
    finally:
        conn.close()


def test_glitched_quote_retries_and_keeps_the_clean_attempt(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-quote-retry-model")
    quote = "The observatory installed a new infrared telescope this spring."
    _, prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, quote)
    outputs = iter(
        [
            _model_output(
                [{"type": "tech_change", "evidence": quote.replace("telescope", "telescopx"), "about_company": True}]
            ),
            _model_output(
                [{"type": "tech_change", "evidence": quote, "about_company": True}]
            ),
        ]
    )
    prompts = []
    options_sent = []

    def handler(request):
        payload = json.loads(request.content)
        prompts.append(payload["messages"][-1]["content"])
        options_sent.append(payload["options"])
        return _chat_response(next(outputs))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["quote_retries"] == 1
    assert body["signals"] == [
        {"type": "tech_change", "evidence": quote, "about_company": True}
    ]
    assert body["drop_counts"]["quote"] == 0
    assert len(prompts) == 2
    assert prompts[0] == prompts[1]
    assert [options["seed"] for options in options_sent] == [42, 43]
    assert [options["temperature"] for options in options_sent] == [0.0, 0.2]
    assert all(options["repeat_penalty"] == 1.0 for options in options_sent)
    conn = db.connect()
    try:
        run = db.get_signal_run(conn, body["id"])
        assert run["quote_retries"] == 1
        stored = conn.execute(
            "SELECT evidence FROM signals WHERE signal_run_id = ?", (body["id"],)
        ).fetchall()
        assert [row["evidence"] for row in stored] == [quote]
        inference = conn.execute(
            "SELECT temperature, seed, repeat_penalty FROM inference_log "
            "WHERE task = ? ORDER BY id",
            (f"signals:{body['id']}",),
        ).fetchall()
        assert [tuple(row) for row in inference] == [
            (0.0, 42, 1.0),
            (0.2, 43, 1.0),
        ]
    finally:
        conn.close()


def test_stray_token_evidence_triggers_quote_retry_without_repairing_quote(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-stray-token-model")
    source_quote = "The team adopted B2B software for its support queue."
    artifact_quote = "The team adopted B2: B2B software for its support queue."
    _, prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, source_quote)
    artifact = signal_workflow.ProspectSignal.model_validate(
        {"type": "tech_change", "evidence": artifact_quote, "about_company": True}
    )
    kept, drops, details = signal_workflow._kept_signals(source_quote, [artifact])
    assert kept == []
    assert drops["quote"] == 1
    assert details[0]["evidence"] == artifact_quote

    outputs = iter(
        [
            _model_output(
                [{"type": "tech_change", "evidence": artifact_quote, "about_company": True}]
            ),
            _model_output(
                [{"type": "tech_change", "evidence": source_quote, "about_company": True}]
            ),
        ]
    )
    options_sent = []

    def handler(request):
        payload = json.loads(request.content)
        options_sent.append(payload["options"])
        return _chat_response(next(outputs))

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    body = response.json()
    assert body["quote_retries"] == 1
    assert [item["evidence"] for item in body["signals"]] == [source_quote]
    assert [options["seed"] for options in options_sent] == [42, 43]
    assert [options["temperature"] for options in options_sent] == [0.0, 0.2]
    conn = db.connect()
    try:
        stored = conn.execute(
            "SELECT evidence FROM signals WHERE signal_run_id = ?", (body["id"],)
        ).fetchall()
        assert [row["evidence"] for row in stored] == [source_quote]
    finally:
        conn.close()


def test_fabricated_evidence_is_dropped_by_quote_verification(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-quote-model")
    _, prospect_id = _new_prospect(
        db_path,
        monkeypatch,
        tmp_path,
        "The organization continues its established water-quality monitoring program.",
    )

    def handler(request):
        return _chat_response(
            _model_output(
                [
                    {
                        "type": "funding",
                        "evidence": "The organization raised a fresh $90 million round.",
                        "about_company": True,
                    }
                ]
            )
        )

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    body = response.json()
    assert body["signals"] == []
    assert body["drop_counts"]["quote"] == 1
    assert body["quote_retries"] == 2
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
        attempts = conn.execute(
            "SELECT seed, temperature FROM inference_log WHERE task = ? ORDER BY id",
            (f"signals:{body['id']}",),
        ).fetchall()
        assert [tuple(row) for row in attempts] == [(42, 0.0), (43, 0.2), (44, 0.2)]
    finally:
        conn.close()


def test_normalized_but_not_verbatim_quote_is_rejected(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-verbatim-model")
    source = "Acme raised new capital in 2026."
    _, prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, source)

    def handler(request):
        return _chat_response(
            _model_output(
                [{"type": "funding", "evidence": "ACME raised new capital in 2026", "about_company": True}]
            )
        )

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    assert response.json()["signals"] == []
    assert response.json()["drop_counts"]["quote"] == 1


def test_negated_signal_is_not_kept_when_quote_omits_sentence_context(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-negation-model")
    source = "The board decided against the second site expansion."
    quote = "second site expansion"
    _, prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, source)

    def handler(request):
        return _chat_response(
            _model_output(
                [{"type": "expansion", "evidence": quote, "about_company": True}]
            )
        )

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 200
    body = response.json()
    assert body["signals"] == []
    assert body["drop_counts"]["negated"] == 1
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
    finally:
        conn.close()


def test_stale_announcement_and_other_company_are_dropped(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-trap-model")
    stale_quote = "The company announced a service-center expansion in April 2010."
    _, stale_prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, stale_quote)
    other_company_quote = "Trade roundup: Rivermark Tools opened a new assembly plant this year."
    _, other_prospect_id = _new_prospect(db_path, monkeypatch, tmp_path, other_company_quote)
    contents = iter(
        [
            _model_output(
                [{"type": "expansion", "evidence": stale_quote, "about_company": True}]
            ),
            _model_output(
                [{"type": "expansion", "evidence": other_company_quote, "about_company": False}]
            ),
        ]
    )

    def handler(request):
        return _chat_response(next(contents))

    _use_mock_transport(monkeypatch, handler)
    stale_response = _post(f"/api/prospects/{stale_prospect_id}/signals")
    other_response = _post(f"/api/prospects/{other_prospect_id}/signals")

    assert stale_response.status_code == 200
    assert stale_response.json()["signals"] == []
    assert stale_response.json()["drop_counts"]["stale"] == 1
    assert other_response.status_code == 200
    assert other_response.json()["signals"] == []
    assert other_response.json()["drop_counts"]["other_company"] == 1


def test_preprocessor_reports_exact_truncated_tail():
    page = "A" * 9 + "TAIL"
    submitted, removed = signal_workflow.prepare_page(page, max_chars=9)
    assert submitted == "A" * 9
    assert removed["truncation"] == {"reason": "character_limit", "text": "TAIL"}
    assert removed["source_characters"] == 13
    assert removed["submitted_characters"] == 9


def test_ollama_outage_queues_and_replays_signal_run(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-queue-model")
    _, prospect_id = _new_prospect(
        db_path, monkeypatch, tmp_path, "The aquarium began a new coral-restoration program."
    )

    def unavailable(request):
        raise httpx.ConnectError("local model is stopped", request=request)

    _use_mock_transport(monkeypatch, unavailable)
    queued_response = _post(f"/api/prospects/{prospect_id}/signals")
    assert queued_response.status_code == 202
    queued = queued_response.json()
    assert queued["status"] == "queued"
    assert queued["signals"] is None
    assert queued["drop_counts"] is None
    assert "OllamaUnavailable" in queued["error"]
    assert queued["queue_task_id"] is not None
    assert queued["model_name"] == "signal-queue-model"

    conn = db.connect()
    try:
        task = db.get_task(conn, queued["queue_task_id"])
        payload = json.loads(task["payload_json"])
        assert task["status"] == "queued"
        assert payload == {
            "prospect_id": prospect_id,
            "product_id": queued["product_id"],
            "signal_run_id": queued["id"],
            "model_name": "signal-queue-model",
        }
    finally:
        conn.close()

    def healthy(request):
        return _chat_response(_model_output([]))

    _use_mock_transport(monkeypatch, healthy)
    import app.queue_worker as queue_worker

    monkeypatch.setattr(queue_worker, "ollama_up", lambda: True)
    previous = HANDLERS.get(signal_workflow.TASK_TYPE)
    signal_workflow.register_signals_handler()
    try:
        assert QueueWorker().run_once() == 1
    finally:
        if previous is None:
            HANDLERS.pop(signal_workflow.TASK_TYPE, None)
        else:
            HANDLERS[signal_workflow.TASK_TYPE] = previous

    completed = _get(f"/api/prospects/{prospect_id}/signals").json()
    assert completed["status"] == "succeeded"
    assert completed["signals"] == []
    assert completed["drop_counts"]["type"] == 0
    conn = db.connect()
    try:
        assert db.get_task(conn, queued["queue_task_id"])["status"] == "done"
        assert db.get_signal_run(conn, queued["id"])["status"] == "succeeded"
    finally:
        conn.close()


def test_invalid_output_failure_is_persisted_without_default_signals(
    db_path, monkeypatch, tmp_path
):
    monkeypatch.setenv("DEFAULT_MODEL", "signal-invalid-model")
    _, prospect_id = _new_prospect(
        db_path, monkeypatch, tmp_path, "The firm describes its ordinary daily operations."
    )
    calls = []

    def handler(request):
        calls.append(request)
        return _chat_response("this is not valid JSON")

    _use_mock_transport(monkeypatch, handler)
    response = _post(f"/api/prospects/{prospect_id}/signals")

    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert body["signals"] is None
    assert body["drop_counts"] is None
    assert body["error"] and "InvalidJsonResponse" in body["error"]
    assert len(calls) == 3
    assert _get(f"/api/prospects/{prospect_id}/signals").json() == body
    conn = db.connect()
    try:
        run = db.get_signal_run(conn, body["id"])
        assert run["status"] == "failed"
        assert run["signals_json"] is None
        assert run["drop_counts_json"] is None
        assert run["removed_content_json"] is not None
        assert "InvalidJsonResponse" in run["error"]
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
    finally:
        conn.close()
