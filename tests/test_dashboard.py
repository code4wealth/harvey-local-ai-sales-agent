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
    assert "View profile" in html
    assert "View ICP" in html
    assert "View latest signals" in html
    assert "View latest draft" in html
    assert "Generate problem statement" in html
    assert "View latest problem statement" in html
    assert "Retry queued tasks" in html
    assert "id=\"hardware\"" in html
    assert "id=\"traceability\"" in html
    assert 'data-type="software"' in html
    assert 'name="page-type" content="software"' in html
    assert 'name="site-kind" content="software"' in html
    assert 'id="product-form-status" class="sr-only" role="status"' in html
    assert 'id="reply-form-status" class="sr-only" role="status"' in html
    assert 'role="status" aria-live="polite">Waiting for a workflow' in html
    assert 'form.reset()' in html
    assert "git_commit" in html
    assert "prompt_hashes" in html
    assert "fetch(" in html
    assert "<script src=" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_dashboard_controls_are_wired_to_same_origin_workflows_and_status():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/")

    html = asyncio.run(request()).text
    expected_bindings = (
        '$("product-form").onsubmit =',
        'const form = event.currentTarget;',
        'formStatus.textContent = "Creating product."',
        'Reply classification complete.',
        'products.onchange = () => loadProspects()',
        'await api(`/api/products/${productId()}/prospects`)',
        'document.querySelectorAll("[data-workflow]")',
        'document.querySelectorAll("[data-view-workflow]")',
        '$("signals").onclick =',
        '$("view-signals").onclick =',
        '$("ranking").onclick =',
        '$("draft").onclick =',
        '$("view-draft").onclick =',
        '$("problem-statement").onclick =',
        '$("view-problem-statement").onclick =',
        'problem-statement`',
        '$("reply-form").onsubmit =',
        '$("retry-queue").onclick =',
        'run(`/api/products/${productId()}/ranking`)',
        'run(`/api/replies/${id}/classification`, "POST")',
        'run("/api/queue/retry", "POST")',
        'const WORKFLOW_POLL_INTERVAL_MS = 2000;',
        'const WORKFLOW_MAX_WAIT_MS = 10 * 60 * 1000;',
        'api(`/api/workflow-runs/${current.id}`)',
        'Queued · waiting for local Ollama',
        'Request failed: ${error.message}',
        'latest.seed',
        'latest.model',
        'hashes.signals',
        'hashes.replies',
        's.git_commit',
        's.hardware',
    )
    for binding in expected_bindings:
        assert binding in html, f"missing dashboard click/status wiring: {binding}"
