from __future__ import annotations

import asyncio

import httpx

from app import db, main as main_module
from app.main import app


def test_same_origin_mutations_are_allowed_and_cross_origin_mutations_rejected(db_path):
    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            cross_origin = await client.post(
                "/api/products",
                json={"name": "Blocked cross-origin product"},
                headers={"Origin": "https://attacker.example"},
            )
            fetch_metadata = await client.post(
                "/api/products",
                json={"name": "Blocked fetch metadata product"},
                headers={"Sec-Fetch-Site": "cross-site"},
            )
            same_origin = await client.post(
                "/api/products",
                json={"name": "Allowed same-origin product"},
                headers={"Origin": "http://127.0.0.1"},
            )
        return cross_origin, fetch_metadata, same_origin

    cross_origin, fetch_metadata, same_origin = asyncio.run(exercise())
    assert cross_origin.status_code == 403
    assert fetch_metadata.status_code == 403
    assert same_origin.status_code == 201
    conn = db.connect()
    try:
        assert [row["name"] for row in db.list_products(conn)] == [
            "Allowed same-origin product"
        ]
    finally:
        conn.close()


def test_host_allowlist_blocks_arbitrary_hosts_and_allows_arena_preview(db_path):
    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            rejected = await client.post(
                "/api/products",
                json={"name": "Untrusted host product"},
                headers={"Host": "attacker.example", "Origin": "http://attacker.example"},
            )
            preview_health = await client.get(
                "/health", headers={"Host": "8000-sandbox.e2b.app"}
            )
            preview_mutation = await client.post(
                "/api/products",
                json={"name": "Arena preview product"},
                headers={
                    "Host": "8000-sandbox.e2b.app",
                    "Origin": "https://8000-sandbox.e2b.app",
                    "X-Forwarded-Proto": "https",
                },
            )
        return rejected, preview_health, preview_mutation

    rejected, preview_health, preview_mutation = asyncio.run(exercise())
    assert rejected.status_code == 400
    assert preview_health.status_code == 200
    assert preview_mutation.status_code == 201


def test_csv_and_page_request_bodies_are_bounded_while_streaming(db_path):
    async def oversized_page_chunks():
        yield b"x" * main_module.MAX_PROSPECT_PAGE_BYTES
        yield b"y"

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            csv_response = await client.post(
                "/api/products/999/prospects/import",
                content=b"x" * (main_module.MAX_PROSPECT_CSV_BYTES + 1),
                headers={"Content-Type": "text/csv"},
            )
            page_response = await client.put(
                "/api/prospects/999/page",
                content=oversized_page_chunks(),
                headers={"Content-Type": "text/plain"},
            )
        return csv_response, page_response

    csv_response, page_response = asyncio.run(exercise())
    assert csv_response.status_code == 413
    assert page_response.status_code == 413
    assert "prospect CSV exceeds" in csv_response.json()["detail"]
    assert "prospect page text exceeds" in page_response.json()["detail"]
