from __future__ import annotations

import asyncio

import httpx

from app.main import app


def test_root_serves_embedded_local_only_dashboard():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Create product" in html
    assert "/api/products" in html
    assert "/api/replies/" in html
    assert "Create unsent draft" in html
    assert "fetch(" in html
    assert "<script src=" not in html
    assert "http://" not in html
    assert "https://" not in html
