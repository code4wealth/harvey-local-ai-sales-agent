from __future__ import annotations

import asyncio

import httpx

from app import db
from app.main import app


def test_product_name_is_case_insensitive_and_duplicate_returns_409(db_path):
    async def create_both():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/api/products",
                json={"name": "Dairy Milk", "description": "first"},
            )
            duplicate = await client.post(
                "/api/products",
                json={"name": "  dAiRy mIlK  ", "description": "duplicate"},
            )
        return first, duplicate

    first, duplicate = asyncio.run(create_both())
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Product already exists"}


def test_delete_product_cascades_data_and_fails_queued_tasks(db_path):
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="Remove me")
        now = db.utcnow()
        prospect_cursor = conn.execute(
            "INSERT INTO prospects (product_id, company_name, created_at) VALUES (?, ?, ?)",
            (product_id, "Example prospect", now),
        )
        prospect_id = int(prospect_cursor.lastrowid)
        task_id = db.enqueue_task(
            conn,
            "workflow.test",
            {"product_id": product_id, "prospect_id": prospect_id},
        )
        conn.commit()
    finally:
        conn.close()

    async def delete_product():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.delete(f"/api/products/{product_id}")

    response = asyncio.run(delete_product())
    assert response.status_code == 204

    conn = db.connect()
    try:
        assert db.get_product(conn, product_id) is None
        assert conn.execute(
            "SELECT COUNT(*) FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()[0] == 0
        task = db.get_task(conn, task_id)
        assert task["status"] == "failed"
        assert "Product was deleted" in task["last_error"]
    finally:
        conn.close()
