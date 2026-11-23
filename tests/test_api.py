from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app import db, llm_client, prospects
from app.main import app


def test_system_routes_report_status_and_hardware(db_path, monkeypatch):
    def ollama_handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    def ollama_client(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(ollama_handler),
        )

    monkeypatch.setattr(llm_client, "_client", ollama_client)

    async def get_routes():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            status_response = await client.get("/api/status")
            hardware_response = await client.get("/api/hardware")
        return status_response, hardware_response

    status_response, hardware_response = asyncio.run(get_routes())
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["service"] == "ok"
    assert status["ai_mode"] == "local-only"
    assert status["ollama"]["available"] is True
    assert status["ollama"]["state"] == "available"
    assert status["ollama"]["url"] == "http://127.0.0.1:11434"
    assert status["queue"] == {"queued": 0, "running": 0, "done": 0, "failed": 0}
    assert status["hardware"]["cpu_count"] >= 1

    assert hardware_response.status_code == 200
    hardware = hardware_response.json()
    assert set(hardware) == {
        "ram_gb", "cpu_count", "gpu_vram_gb", "tier", "recommended_model", "recommended_num_ctx"
    }
    assert hardware["cpu_count"] >= 1
    assert hardware["recommended_model"].startswith("qwen3:")
    assert hardware["recommended_num_ctx"] in {2048, 4096, 8192}


def test_status_distinguishes_slow_ollama_from_unavailable(db_path, monkeypatch):
    def slow_handler(request):
        raise httpx.ReadTimeout("model is still loading", request=request)

    def ollama_client(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(slow_handler),
        )

    monkeypatch.setattr(llm_client, "_client", ollama_client)

    async def get_status():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/status")

    response = asyncio.run(get_status())
    assert response.status_code == 200
    status = response.json()["ollama"]
    assert status["state"] == "slow"
    assert status["available"] is None
    assert "model may still be loading" in status["message"]
    assert "did not answer" in status["message"]


def test_status_shows_last_generation_timeout_as_slow_when_probe_is_up(db_path, monkeypatch):
    conn = db.connect()
    try:
        db.log_inference(
            conn,
            task="slow-model-test",
            model="qwen3:4b",
            host=llm_client.OLLAMA_URL,
            status="error:timeout",
        )
    finally:
        conn.close()

    def healthy_handler(request):
        return httpx.Response(200, json={"models": []})

    def ollama_client(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(healthy_handler),
        )

    monkeypatch.setattr(llm_client, "_client", ollama_client)

    async def get_status():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/status")

    response = asyncio.run(get_status())
    status = response.json()["ollama"]
    assert status["available"] is True
    assert status["state"] == "slow"
    assert status["last_inference"]["task"] == "slow-model-test"
    assert status["last_inference"]["status"] == "error:timeout"


def test_status_does_not_keep_old_timeout_as_slow(db_path, monkeypatch):
    conn = db.connect()
    try:
        inference_id = db.log_inference(
            conn,
            task="old-timeout-test",
            model="qwen3:4b",
            host=llm_client.OLLAMA_URL,
            status="error:timeout",
        )
        created_at = (datetime.now(timezone.utc) - timedelta(minutes=5, seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        conn.execute(
            "UPDATE inference_log SET created_at = ? WHERE id = ?",
            (created_at, inference_id),
        )
        conn.commit()
    finally:
        conn.close()

    def healthy_handler(request):
        return httpx.Response(200, json={"models": []})

    def ollama_client(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(healthy_handler),
        )

    monkeypatch.setattr(llm_client, "_client", ollama_client)

    async def get_status():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/status")

    response = asyncio.run(get_status())
    assert response.status_code == 200
    status = response.json()["ollama"]
    assert status["available"] is True
    assert status["state"] == "available"


def test_status_reports_connect_failure_as_unavailable(db_path, monkeypatch):
    def unavailable_handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    def ollama_client(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(unavailable_handler),
        )

    monkeypatch.setattr(llm_client, "_client", ollama_client)

    async def get_status():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/status")

    response = asyncio.run(get_status())
    assert response.status_code == 200
    status = response.json()["ollama"]
    assert status["state"] == "unavailable"
    assert status["available"] is False
    assert "message" not in status


def test_product_prospect_csv_and_local_page_routes(db_path, monkeypatch, tmp_path):
    monkeypatch.setattr(prospects, "DEFAULT_PAGE_DIR", tmp_path / "pages")

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            product_response = await client.post(
                "/api/products", json={"name": "Harvey CRM", "description": "Local sales tool"}
            )
            product_id = product_response.json()["id"]
            csv_content = (
                "company_name,contact_name,contact_title,employee_count,do_not_contact\n"
                "Acme,Ada,VP Sales,25,false\n"
            )
            import_response = await client.post(
                f"/api/products/{product_id}/prospects/import",
                content=csv_content,
                headers={"content-type": "text/csv"},
            )
            duplicate_import_response = await client.post(
                f"/api/products/{product_id}/prospects/import",
                content=csv_content,
                headers={"content-type": "text/csv"},
            )
            prospect = (await client.get(f"/api/products/{product_id}/prospects")).json()[0]
            prospect_id = prospect["id"]
            saved_page = await client.put(
                f"/api/prospects/{prospect_id}/page",
                content="A local page excerpt.",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
            loaded_page = await client.get(f"/api/prospects/{prospect_id}/page")
            detail = await client.get(f"/api/prospects/{prospect_id}")
            score_response = await client.post(f"/api/prospects/{prospect_id}/score")
        return (
            product_response, import_response, duplicate_import_response, prospect,
            saved_page, loaded_page, detail, score_response,
        )

    (
        product_response, import_response, duplicate_import_response, prospect,
        saved_page, loaded_page, detail, score_response,
    ) = asyncio.run(exercise())
    assert product_response.status_code == 201
    assert product_response.json()["name"] == "Harvey CRM"
    assert import_response.status_code == 201
    assert import_response.json()["imported"] == 1
    assert import_response.json()["skipped"] == 0
    assert duplicate_import_response.status_code == 201
    assert duplicate_import_response.json()["imported"] == 0
    assert duplicate_import_response.json()["skipped"] == 1
    assert prospect["company_name"] == "Acme"
    assert prospect["employee_count"] == 25
    assert prospect["do_not_contact"] == 0
    assert saved_page.status_code == 200
    assert loaded_page.status_code == 200
    assert loaded_page.text == "A local page excerpt."
    assert detail.json()["id"] == prospect["id"]
    assert score_response.status_code == 202
    assert score_response.json()["requires_ollama"] is False


def test_status_reports_ollama_http_failure_separately(db_path, monkeypatch):
    def failing_handler(request):
        return httpx.Response(503, text="service temporarily unavailable")

    def ollama_client(timeout):
        return httpx.Client(
            base_url=llm_client.OLLAMA_URL,
            timeout=timeout,
            transport=httpx.MockTransport(failing_handler),
        )

    monkeypatch.setattr(llm_client, "_client", ollama_client)

    async def get_status():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/status")

    response = asyncio.run(get_status())
    assert response.status_code == 200
    status = response.json()["ollama"]
    assert status["state"] == "error"
    assert status["available"] is False
    assert "HTTP 503" in status["message"]
