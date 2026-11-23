from __future__ import annotations

import asyncio

import httpx

from app import llm_client
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
    assert status["ollama"]["url"] == "http://127.0.0.1:11434"
    assert status["queue"] == {"queued": 0, "running": 0, "done": 0, "failed": 0}
    assert status["hardware"]["cpu_count"] >= 1

    assert hardware_response.status_code == 200
    hardware = hardware_response.json()
    assert set(hardware) == {"ram_gb", "cpu_count", "gpu_vram_gb", "tier", "recommended_model"}
    assert hardware["cpu_count"] >= 1
    assert hardware["recommended_model"].startswith("qwen3:")
