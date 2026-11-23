from __future__ import annotations

import asyncio

import httpx

from app import db, llm_client
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
