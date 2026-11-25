from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx

from app.main import app


def test_operations_route_serves_embedded_local_only_dashboard():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            return await client.get("/operations")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Create product" in html
    assert 'id="create-product-button"' in html
    assert 'id="product-form-error" class="form-error" role="alert"' in html
    assert "Delete product" in html
    assert "/api/products" in html
    assert "/api/replies/" in html
    assert "Draft Email" in html
    assert "View Email Draft" in html
    assert 'id="prospect-import-form"' in html
    assert 'id="prospect-csv"' in html
    assert 'id="pipeline-prospect-limit" type="number" min="1" step="1" value="3"' in html
    assert "Default: 3 prospects." in html
    assert "stable ID order" in html
    assert 'id="output" class="result-content"' in html
    assert "Technical details" in html
    assert "Prompt hash" in html
    assert "Commit hash" in html
    assert "Email subject" in html
    assert "Reply label" in html
    assert "Model-derived: ICP embedding similarity and signal type/confidence." in html
    assert "Rule-based: size/title fit, quote verification, component weighting, tiers, and evidence-quality checks." in html
    assert "Evidence quality is an audit indicator, not extra score points." in html
    assert "Score explanation, rules, and evidence" in html
    assert "View profile" in html
    assert "View ICP" in html
    assert "View latest signals" in html
    assert "View Email Draft" in html
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


def test_operations_controls_are_wired_to_same_origin_workflows_and_status():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            return await client.get("/operations")

    html = asyncio.run(request()).text
    expected_bindings = (
        '$("product-form").onsubmit =',
        'const form = event.currentTarget;',
        'submitButton.disabled = true;',
        'formError.textContent = message;',
        'window.confirm(`Delete ${name} and its stored prospects, research, Email Drafts, and workflow history?`)',
        'await api(`/api/products/${id}`, { method: "DELETE" });',
        'formStatus.textContent = "Creating product."',
        'Reply classification complete.',
        'products.onchange = () => {',
        'return loadProspects().catch(error => {',
        'await api(`/api/products/${productId()}/prospects`)',
        '$("prospect-csv").onchange =',
        '$("prospect-import-form").onsubmit = async event =>',
        'api(`/api/products/${encodeURIComponent(selectedProductId)}/prospects/import`',
        'CSV files must be 5 MB or smaller.',
        'document.querySelectorAll("[data-workflow]")',
        'document.querySelectorAll("[data-view-workflow]")',
        'const requestedLimit = Number(control.value);',
        'Number.isSafeInteger(requestedLimit) || requestedLimit < 1',
        '`/api/products/${product}/pipeline?prospect_limit=${requestedLimit}`',
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
        'function friendlyWorkflowError(error, status)',
        'Ollama is not running. Task queued. Start Ollama, then click Retry queued tasks.',
        'The local model returned data that did not match the required format.',
        'latest.seed',
        'latest.model',
        'latest.prompt_hash',
        'latest.commit_hash',
        'hashes.signals',
        'hashes.replies',
        's.git_commit',
        's.hardware',
    )
    for binding in expected_bindings:
        assert binding in html, f"missing dashboard click/status wiring: {binding}"


def test_root_serves_sellbird_react_dashboard_and_bundled_assets():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            page = await client.get("/")
            paths = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.text)
            assets = [await client.get(path) for path in paths]
            notices = await client.get("/licenses/THIRD_PARTY_NOTICES.txt")
            return page, assets, notices

    page, assets, notices = asyncio.run(request())
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "Sellbird AI · Local Sales Intelligence" in page.text
    assert 'id="root"' in page.text
    assert assets and all(asset.status_code == 200 for asset in assets)
    bundle_text = "\n".join(asset.text for asset in assets)
    for label in (
        "PREVIEW DATA",
        "localhost:11434",
        "SQLite",
        "Dashboard",
        "Products",
        "Prospects",
        "Prospect Research",
        "Email Drafts",
        "Draft Email",
        "Generate Email Draft",
        "never auto-sent",
        "There is no Send button",
        "Reply Classifier",
        "Activity Queue",
        "Local AI & Models",
        "General Settings",
        "General & Storage",
        "Installed Ollama Models",
        "ICP Fit Score Threshold",
        "Signal Confidence Requirement",
        "Playwright Web Scraper",
        "Local Vector Index",
        "Service health",
        "Runtime configuration",
        "DEMO ONLY",
        "Draft-Only Workspace",
        "Draft-Only · Stored in Local SQLite",
        "Draft-Only · Browser Preview",
        "Needs More Information",
        "Follow-up Later",
        "Classify reply",
        "Draft follow-up",
    ):
        assert label.lower() in bundle_text.lower()
    assert "Workflow Console" not in bundle_text
    assert "Open Draft Workflow" not in bundle_text
    styles = next(asset.text for asset in assets if asset.headers["content-type"].startswith("text/css"))
    normalized_styles = styles.lower()
    for color in ("#fff", "#f8fafc", "#f1f5f9", "#e2e8f0", "#4f46e5", "#4338ca", "#eef2ff", "#10b981", "#f59e0b", "#e11d48", "#111827"):
        assert color in normalized_styles
    # Vite's production CSS minifier shortens white from #ffffff to #fff.
    assert re.search(r"--canvas:#f8fafc(?:[;}])", normalized_styles)
    assert re.search(r"--sidebar:#(?:fff|ffffff)(?:[;}])", normalized_styles)
    assert re.search(r"--paper:#(?:fff|ffffff)(?:[;}])", normalized_styles)
    assert "--recess:#f1f5f9" in normalized_styles
    assert "--border:#e2e8f0" in normalized_styles
    assert "--charcoal:#111827" in normalized_styles
    assert "color-scheme:light" in normalized_styles
    assert "inter variable" in normalized_styles
    assert "jetbrains mono variable" in normalized_styles
    assert "ibm plex mono" not in normalized_styles
    assert "--color-brand-500:#4f46e5" in normalized_styles
    assert "--color-brand-600:#4338ca" in normalized_styles
    assert "--color-slate-50:#f8fafc" in normalized_styles
    assert "--color-slate-100:#f1f5f9" in normalized_styles
    assert "--color-slate-200:#e2e8f0" in normalized_styles
    assert "--qwen-synthesis-background:#f5f7ff" in normalized_styles
    assert "#2ea3f2" not in normalized_styles
    assert "#0284c7" not in normalized_styles
    assert "#22c55e" not in normalized_styles
    assert "#dc2626" not in normalized_styles
    assert ".precision-slider-card" in normalized_styles
    assert ".subsystem-connection-list" in normalized_styles
    assert ".tick-gauge-mark" in normalized_styles
    assert "56px" in normalized_styles
    assert "sparkline-kpi-card" in normalized_styles
    assert "key-value-config-panel" in normalized_styles
    assert "dark-status-danger" in normalized_styles
    assert "ai-synthesis-block" in normalized_styles
    assert ".ai-synthesis-qwen3" in normalized_styles
    assert "--qwen-synthesis-text:#4f46e5" in normalized_styles
    generic_synthesis_rule = re.search(r"\.ai-synthesis-generated\{([^}]+)\}", normalized_styles)
    assert generic_synthesis_rule and "#4f46e5" not in generic_synthesis_rule.group(1)
    assert ".ai-synthesis-qwen3{" in normalized_styles
    assert ".btn-ai{border-color:var(--brand);color:#fff;background:var(--brand)}" in normalized_styles
    assert ".btn-primary,.btn-dark{border-color:var(--charcoal);color:#fff;background:var(--charcoal)}" in normalized_styles
    assert ".draft-storage-indicator.is-persisted" in normalized_styles
    assert ".draft-storage-indicator.is-preview" in normalized_styles
    assert ".reply-next-step-link" in normalized_styles
    assert "max-width:700px" in normalized_styles
    assert "max-width:430px" in normalized_styles
    assert "backdrop-filter:none!important" in normalized_styles
    assert notices.status_code == 200
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in notices.text
    assert "SIL OPEN FONT LICENSE Version 1.1" in notices.text
    assert "https://" not in page.text


def test_operations_console_remains_available_separately():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            return await client.get("/operations")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert 'id="product-panel"' in response.text
    assert 'id="prospect-panel"' in response.text
    assert 'id="prospect-import-form"' in response.text
    assert 'id="reply-panel"' in response.text


def test_dashboard_routes_reach_model_settings_and_existing_workflows():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            settings = await client.get("/settings/models")
            products = await client.get("/products")
            prospects = await client.get("/prospects")
            prospect_import = await client.get("/prospects/import")
            research = await client.get("/research/P-1042")
            campaigns = await client.get("/campaigns")
            replies = await client.get("/replies")
            activity = await client.get("/activity")
            general = await client.get("/settings/general")
            operations = await client.get("/operations")
            return settings, products, prospects, prospect_import, research, campaigns, replies, activity, general, operations

    settings, products, prospects, prospect_import, research, campaigns, replies, activity, general, operations = asyncio.run(request())
    for response in (settings, products, prospects, research, campaigns, replies, activity, general):
        assert response.status_code == 200
        assert 'id="root"' in response.text
    assert prospect_import.status_code == 307
    assert prospect_import.headers["location"] == "/prospects?import=true"
    assert operations.status_code == 200
    assert 'id="prospect-panel"' in operations.text


def test_draft_and_reply_workflows_preserve_local_storage_provenance():
    frontend = Path(__file__).resolve().parents[1] / "frontend" / "src"
    campaigns = (frontend / "pages" / "CampaignsPage.jsx").read_text(encoding="utf-8")
    replies = (frontend / "pages" / "RepliesPage.jsx").read_text(encoding="utf-8")
    context = (frontend / "WorkspaceContext.jsx").read_text(encoding="utf-8")
    ui = (frontend / "ui.jsx").read_text(encoding="utf-8")

    assert "apiRequest(`/api/products/${encodeURIComponent(selectedProspect.productId)}/prospects/${encodeURIComponent(selectedProspect.id)}/draft`)" in campaigns
    assert 'result?.status !== "succeeded"' in campaigns
    assert "result.id == null" in campaigns
    assert "result.status === \"succeeded\" && result.id != null" in campaigns
    assert "sqliteDraftSnapshot?.id != null" in campaigns
    assert "savedDraft.backendDraftId != null" in campaigns
    assert "const isPersisted = Boolean(sqliteDraftSnapshot" in campaigns
    assert "Draft-Only · Stored in Local SQLite" in campaigns
    assert "Draft-Only · Browser Preview" in campaigns
    assert "new: \"true\"" in campaigns
    assert "to={`/replies?prospectId=${encodeURIComponent(selectedProspect.id)}`}" in campaigns
    assert "mode=followup" in replies
    assert '"Needs More Information"' in replies
    assert '"Follow-up Later"' in replies
    assert "isPersisted: false" in context
    assert "backendDraftId: null" in context
    assert "const isQwen3Generated = isGenerated && Boolean(reportedModel)" in ui
    assert "workspace.activeModel" not in ui
