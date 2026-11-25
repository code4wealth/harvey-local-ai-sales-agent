"""FastAPI entry point for the local Harvey service."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import batch, db, hardware, llm_client, local_paths, prospects
from app.queue_worker import QueueWorker
from app.workflows import icp as icp_workflow
from app.workflows import pipeline as pipeline_workflow
from app.workflows import profile as profile_workflow
from app.workflows import ranking as ranking_workflow
from app.workflows import replies as reply_workflow
from app.workflows import register_workflow_handlers
from app.workflows import common as workflow_common
from app.workflows import draft as draft_workflow
from app.workflows import problem_statement as problem_statement_workflow
from app.workflows import signals as signal_workflow

logger = logging.getLogger("harvey.main")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    conn = db.connect()
    try:
        db.init_db(conn)
        interrupted_runs = db.fail_interrupted_workflow_runs(conn)
        if interrupted_runs:
            logger.warning("marked %d interrupted workflow run(s) as failed", interrupted_runs)
    finally:
        conn.close()

    batch.register_batch_handlers()
    register_workflow_handlers()
    worker = QueueWorker()
    application.state.queue_worker = worker
    worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(
    title="Harvey Local AI Sales Agent",
    version="0.1.0",
    description="Local-only sales research and outreach backend. AI runs through local Ollama.",
    lifespan=lifespan,
)

# This unauthenticated local service accepts loopback hosts and the Arena
# preview host. Arbitrary Host headers are rejected to reduce DNS-
# rebinding exposure; normal desktop use should still bind Uvicorn to loopback.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "::1", "*.e2b.app"],
)

MAX_PROSPECT_CSV_BYTES = 5 * 1024 * 1024
MAX_PROSPECT_PAGE_BYTES = 1 * 1024 * 1024
_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_tuple(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        scheme = parsed.scheme.lower()
        host = parsed.hostname.rstrip(".").casefold()
        port = parsed.port or (443 if scheme == "https" else 80)
        return scheme, host, port
    except ValueError:
        return None


def _request_origin_tuple(request: Request) -> tuple[str, str, int] | None:
    host = request.headers.get("host", "")
    forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    scheme = forwarded_scheme if forwarded_scheme in {"http", "https"} else request.url.scheme
    return _origin_tuple(f"{scheme}://{host}")


@app.middleware("http")
async def reject_cross_origin_mutations(request: Request, call_next):
    """Reject browser-originated cross-site requests that can mutate local data."""
    if request.method.upper() in _STATE_CHANGING_METHODS:
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site", "").casefold()
        if fetch_site == "cross-site" or (
            origin is not None and _origin_tuple(origin) != _request_origin_tuple(request)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "cross-origin state-changing request blocked"},
            )
    return await call_next(request)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPOSITORY_ROOT / "frontend"
FRONTEND_OPERATIONS = FRONTEND_ROOT / "operations.html"
FRONTEND_STATIC = FRONTEND_ROOT / "static"
FRONTEND_BUILT_INDEX = FRONTEND_STATIC / "index.html"

# Vite emits the production React bundle here. ``check_dir=False`` keeps the
# Python API importable before the optional frontend build has been run.
app.mount(
    "/assets",
    StaticFiles(directory=str(FRONTEND_STATIC / "assets"), check_dir=False),
    name="dashboard-assets",
)
app.mount(
    "/licenses",
    StaticFiles(directory=str(FRONTEND_STATIC / "licenses"), check_dir=False),
    name="dashboard-licenses",
)

PROMPT_HASH_FILES = {
    "signals": REPOSITORY_ROOT / "data" / "eval" / "frozen_signal_prompt.sha256",
    "replies": REPOSITORY_ROOT / "data" / "eval" / "frozen_reply_prompt.sha256",
}


def read_git_commit_hash() -> str:
    """Read the source commit once at app startup; packaged builds may lack Git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    commit = result.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit) else "unknown"


def read_frozen_prompt_hashes() -> dict[str, str]:
    """Read only the two frozen digest files; missing or malformed values stay unknown."""
    hashes: dict[str, str] = {}
    for name, path in PROMPT_HASH_FILES.items():
        try:
            value = path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            value = ""
        hashes[name] = value if re.fullmatch(r"[0-9a-fA-F]{64}", value) else "unknown"
    return hashes


GIT_COMMIT = read_git_commit_hash()


def sellbird_dashboard_entry() -> FileResponse:
    """Serve the built React workspace, falling back to the legacy console before build."""
    dashboard = FRONTEND_BUILT_INDEX if FRONTEND_BUILT_INDEX.is_file() else FRONTEND_OPERATIONS
    return FileResponse(dashboard, media_type="text/html")


@app.get("/", include_in_schema=False)
def api_dashboard() -> FileResponse:
    """Serve the Sellbird dashboard, with the local workflow console kept separate."""
    return sellbird_dashboard_entry()


@app.get("/operations", include_in_schema=False)
def api_operations() -> FileResponse:
    """Serve the existing local product and prospect workflow console."""
    return FileResponse(FRONTEND_OPERATIONS, media_type="text/html")


@app.get("/settings/models", include_in_schema=False)
def api_model_settings() -> FileResponse:
    """Serve the React workspace at the local model settings route."""
    return sellbird_dashboard_entry()


@app.get("/settings/general", include_in_schema=False)
def api_general_settings() -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/products", include_in_schema=False)
def api_products_workspace() -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/prospects/import", include_in_schema=False)
def api_prospect_import_workspace() -> RedirectResponse:
    """Open the React CSV-mapping flow; the older console remains at /operations."""
    return RedirectResponse("/prospects?import=true", status_code=307)


@app.get("/prospects", include_in_schema=False)
def api_prospects_workspace() -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/research", include_in_schema=False)
def api_research_workspace() -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/research/{prospect_id}", include_in_schema=False)
def api_research_dossier(prospect_id: str) -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/campaigns", include_in_schema=False)
def api_campaigns_workspace() -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/replies", include_in_schema=False)
def api_replies_workspace() -> FileResponse:
    return sellbird_dashboard_entry()


@app.get("/activity", include_in_schema=False)
def api_activity_workspace() -> FileResponse:
    return sellbird_dashboard_entry()


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    docs_path: str = Field(default="", max_length=500)


class ProductUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    docs_path: str = Field(default="", max_length=500)


class ReplyTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    model: str | None = Field(default=None, max_length=200)


def _prospect_response(row) -> dict:
    result = dict(row)
    result.pop("page_embedding", None)
    return result


async def _read_limited_body(request: Request, *, max_bytes: int, label: str) -> bytes:
    """Read a request body incrementally and reject it once its byte budget is exceeded."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Content-Length") from exc
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="invalid Content-Length")
        if declared_length > max_bytes:
            raise HTTPException(status_code=413, detail=f"{label} exceeds {max_bytes} bytes")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail=f"{label} exceeds {max_bytes} bytes")
        body.extend(chunk)
    return bytes(body)


def _recent_timeout_inference(row) -> bool:
    if row is None or row["status"] != "error:timeout":
        return False
    try:
        created_at = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - created_at
    return timedelta(0) <= age < timedelta(minutes=5)


@app.post("/api/products", status_code=201, tags=["products"])
def api_create_product(request: ProductCreate) -> dict:
    try:
        docs_path = local_paths.normalize_company_info_path(request.docs_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    conn = db.connect()
    try:
        product_id = db.create_product(
            conn, name=request.name, description=request.description, docs_path=docs_path
        )
        conn.commit()
        product = db.get_product(conn, product_id)
        return dict(product)
    except db.ProductAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="Product already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        conn.close()


@app.put("/api/products/{product_id}", tags=["products"])
def api_update_product(product_id: int, request: ProductUpdate) -> dict:
    try:
        docs_path = local_paths.normalize_company_info_path(request.docs_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    conn = db.connect()
    try:
        product = db.update_product(
            conn,
            product_id=product_id,
            name=request.name,
            description=request.description,
            docs_path=docs_path,
        )
        if product is None:
            raise HTTPException(status_code=404, detail="product not found")
        return dict(product)
    except db.ProductAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="Product already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        conn.close()


@app.get("/api/products", tags=["products"])
def api_list_products() -> list[dict]:
    conn = db.connect()
    try:
        return [dict(product) for product in db.list_products(conn)]
    finally:
        conn.close()


@app.delete("/api/products/{product_id}", status_code=204, tags=["products"])
def api_delete_product(product_id: int) -> Response:
    conn = db.connect()
    try:
        if db.get_product(conn, product_id) is None:
            raise HTTPException(status_code=404, detail="product not found")
        db.fail_tasks_for_product(conn, product_id)
        conn.execute("DELETE FROM products WHERE id = ?", (int(product_id),))
        conn.commit()
        return Response(status_code=204)
    finally:
        conn.close()


def _workflow_run_response(run_id: int) -> dict:
    conn = db.connect()
    try:
        row = db.get_workflow_run(conn, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="workflow run not found")
        return workflow_common.workflow_run_payload(row)
    finally:
        conn.close()


def _post_workflow(product_id: int, *, submit) -> JSONResponse:
    try:
        run_id = submit(product_id)
    except workflow_common.ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except llm_client.OllamaUnavailable as exc:
        run_id = getattr(exc, "workflow_run_id", None)
        if run_id is None:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=_workflow_run_response(int(run_id)))
    except workflow_common.WorkflowRunError as exc:
        payload = _workflow_run_response(exc.run_id)
        return JSONResponse(status_code=502, content=payload)
    payload = _workflow_run_response(run_id)
    status_code = 202 if payload["status"] in {"queued", "running"} else 200
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/workflow-runs/{run_id}", tags=["workflows"])
def api_get_workflow_run(run_id: int) -> dict:
    conn = db.connect()
    try:
        row = db.get_workflow_run(conn, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="workflow run not found")
        return workflow_common.workflow_run_payload(row)
    finally:
        conn.close()


def _get_workflow(product_id: int, workflow: str) -> dict:
    conn = db.connect()
    try:
        if db.get_product(conn, product_id) is None:
            raise HTTPException(status_code=404, detail="product not found")
        row = db.latest_workflow_run(conn, product_id=product_id, workflow=workflow)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"no {workflow} workflow run is stored for this product",
            )
        return workflow_common.workflow_run_payload(row)
    finally:
        conn.close()


@app.post("/api/products/{product_id}/pipeline", tags=["workflows"])
def api_start_product_pipeline(product_id: int, model: str | None = None) -> JSONResponse:
    try:
        payload = pipeline_workflow.submit_pipeline(product_id, model=model)
    except pipeline_workflow.PipelineProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except pipeline_workflow.PipelineQueueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    worker = getattr(app.state, "queue_worker", None)
    if worker is not None:
        worker.wake()
    return JSONResponse(status_code=202, content=payload)


@app.get("/api/pipeline-runs/{run_id}", tags=["workflows"])
def api_get_pipeline_run(run_id: int) -> dict:
    try:
        return pipeline_workflow.read_pipeline_run_payload(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="pipeline run not found") from exc


@app.get("/api/products/{product_id}/pipeline", tags=["workflows"])
def api_get_product_pipeline(product_id: int) -> dict:
    try:
        return pipeline_workflow.latest_pipeline_payload(product_id)
    except pipeline_workflow.PipelineProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/products/{product_id}/profile", tags=["workflows"])
def api_generate_profile(product_id: int) -> JSONResponse:
    return _post_workflow(product_id, submit=profile_workflow.submit_profile)


@app.get("/api/products/{product_id}/profile", tags=["workflows"])
def api_get_profile(product_id: int) -> dict:
    return _get_workflow(product_id, "profile")


@app.post("/api/products/{product_id}/icp", tags=["workflows"])
def api_generate_icp(product_id: int) -> JSONResponse:
    return _post_workflow(product_id, submit=icp_workflow.submit_icp)


@app.get("/api/products/{product_id}/icp", tags=["workflows"])
def api_get_icp(product_id: int) -> dict:
    return _get_workflow(product_id, "icp")


@app.get("/api/products/{product_id}/prospects", tags=["prospects"])
def api_list_prospects(product_id: int) -> list[dict]:
    conn = db.connect()
    try:
        if db.get_product(conn, product_id) is None:
            raise HTTPException(status_code=404, detail="product not found")
        return [_prospect_response(prospect) for prospect in db.list_prospects(conn, product_id)]
    finally:
        conn.close()


@app.get("/api/products/{product_id}/ranking", tags=["ranking"])
def api_rank_product(product_id: int) -> dict:
    try:
        return ranking_workflow.rank_product(product_id)
    except ranking_workflow.ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/products/{product_id}/prospects/import", status_code=201, tags=["prospects"])
async def api_import_prospects(product_id: int, request: Request) -> dict:
    try:
        body = await _read_limited_body(
            request, max_bytes=MAX_PROSPECT_CSV_BYTES, label="prospect CSV"
        )
        csv_text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    conn = db.connect()
    try:
        imported, skipped = prospects.import_prospects_csv(
            conn, product_id=product_id, csv_text=csv_text
        )
        return {"product_id": product_id, "imported": imported, "skipped": skipped}
    except prospects.ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except prospects.ProspectImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="CSV import violates a data constraint") from exc
    finally:
        conn.close()


@app.get("/api/prospects/{prospect_id}", tags=["prospects"])
def api_get_prospect(prospect_id: int) -> dict:
    conn = db.connect()
    try:
        prospect = db.get_prospect(conn, prospect_id)
        if prospect is None:
            raise HTTPException(status_code=404, detail="prospect not found")
        return _prospect_response(prospect)
    finally:
        conn.close()


@app.put("/api/prospects/{prospect_id}/page", tags=["prospects"])
async def api_store_prospect_page(prospect_id: int, request: Request) -> dict:
    try:
        body = await _read_limited_body(
            request, max_bytes=MAX_PROSPECT_PAGE_BYTES, label="prospect page text"
        )
        page_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="page text must be UTF-8 encoded") from exc
    conn = db.connect()
    try:
        page_path = prospects.store_prospect_page(
            conn, prospect_id=prospect_id, text=page_text
        )
        return {"prospect_id": prospect_id, "page_text_path": page_path}
    except prospects.ProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        conn.close()


@app.get("/api/prospects/{prospect_id}/page", response_class=PlainTextResponse, tags=["prospects"])
def api_load_prospect_page(prospect_id: int) -> PlainTextResponse:
    conn = db.connect()
    try:
        page_text = prospects.load_prospect_page(conn, prospect_id)
        return PlainTextResponse(page_text, media_type="text/plain; charset=utf-8")
    except prospects.ProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except prospects.ProspectPageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


def _draft_run_response(run_id: int) -> dict:
    try:
        return draft_workflow.read_draft_run_payload(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="draft run not found") from exc


@app.post(
    "/api/products/{product_id}/prospects/{prospect_id}/draft", tags=["drafts"]
)
def api_create_draft(
    product_id: int, prospect_id: int, model: str | None = None
) -> JSONResponse:
    try:
        payload = draft_workflow.submit_draft(product_id, prospect_id, model=model)
    except draft_workflow.DraftProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except draft_workflow.DraftProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except llm_client.OllamaUnavailable as exc:
        run_id = getattr(exc, "draft_run_id", None)
        if run_id is None:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=_draft_run_response(int(run_id)))
    except draft_workflow.DraftRunError as exc:
        return JSONResponse(status_code=502, content=_draft_run_response(exc.run_id))
    status_code = 202 if payload["status"] == "queued" else 200
    return JSONResponse(status_code=status_code, content=payload)


@app.get(
    "/api/products/{product_id}/prospects/{prospect_id}/draft", tags=["drafts"]
)
def api_get_draft(product_id: int, prospect_id: int) -> dict:
    try:
        return draft_workflow.latest_draft_payload(product_id, prospect_id)
    except draft_workflow.DraftProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except draft_workflow.DraftProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _problem_statement_run_response(run_id: int) -> dict:
    try:
        return problem_statement_workflow.read_problem_statement_payload(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="problem statement run not found") from exc


@app.post(
    "/api/products/{product_id}/prospects/{prospect_id}/problem-statement",
    tags=["problem statements"],
)
def api_create_problem_statement(
    product_id: int, prospect_id: int, model: str | None = None
) -> JSONResponse:
    try:
        payload = problem_statement_workflow.submit_problem_statement(
            product_id, prospect_id, model=model
        )
    except problem_statement_workflow.ProblemStatementProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except problem_statement_workflow.ProblemStatementProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except llm_client.OllamaUnavailable as exc:
        run_id = getattr(exc, "problem_statement_run_id", None)
        if run_id is None:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse(
            status_code=202, content=_problem_statement_run_response(int(run_id))
        )
    except problem_statement_workflow.ProblemStatementRunError as exc:
        return JSONResponse(
            status_code=502, content=_problem_statement_run_response(exc.run_id)
        )
    status_code = 202 if payload["status"] == "queued" else 200
    return JSONResponse(status_code=status_code, content=payload)


@app.get(
    "/api/products/{product_id}/prospects/{prospect_id}/problem-statement",
    tags=["problem statements"],
)
def api_get_problem_statement(product_id: int, prospect_id: int) -> dict:
    try:
        return problem_statement_workflow.latest_problem_statement_payload(
            product_id, prospect_id
        )
    except problem_statement_workflow.ProblemStatementProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except problem_statement_workflow.ProblemStatementProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _signal_run_response(run_id: int) -> dict:
    conn = db.connect()
    try:
        row = db.get_signal_run(conn, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="signal run not found")
        return signal_workflow.signal_run_payload(row)
    finally:
        conn.close()


@app.post("/api/prospects/{prospect_id}/signals", tags=["signals"])
def api_generate_signals(prospect_id: int, model: str | None = None) -> JSONResponse:
    try:
        run_id = signal_workflow.submit_signals(prospect_id, model=model)
    except prospects.ProspectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except llm_client.OllamaUnavailable as exc:
        run_id = getattr(exc, "signal_run_id", None)
        if run_id is None:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=_signal_run_response(int(run_id)))
    except signal_workflow.SignalRunError as exc:
        return JSONResponse(status_code=502, content=_signal_run_response(exc.run_id))
    return JSONResponse(status_code=200, content=_signal_run_response(run_id))


@app.get("/api/prospects/{prospect_id}/signals", tags=["signals"])
def api_get_signals(prospect_id: int) -> dict:
    conn = db.connect()
    try:
        if db.get_prospect(conn, prospect_id) is None:
            raise HTTPException(status_code=404, detail="prospect not found")
        row = db.latest_signal_run(conn, prospect_id)
        if row is None:
            raise HTTPException(status_code=404, detail="no signal run is stored for this prospect")
        return signal_workflow.signal_run_payload(row)
    finally:
        conn.close()


def _reply_classification_response(reply_id: str) -> dict:
    try:
        return reply_workflow.reply_classification_payload(reply_id)
    except reply_workflow.ReplyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/replies/classify-text", tags=["replies"])
def api_classify_reply_text(request: ReplyTextRequest) -> dict:
    """Classify pasted text in memory with local Ollama; do not persist the reply."""
    try:
        result = reply_workflow.classify_reply_text(request.text, model=request.model)
    except llm_client.OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "is_preview": False}


@app.post("/api/replies/{reply_id}/classification", tags=["replies"])
def api_classify_reply(reply_id: str, model: str | None = None) -> JSONResponse:
    try:
        result = reply_workflow.submit_reply_classification(reply_id, model=model)
    except reply_workflow.ReplyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except llm_client.OllamaUnavailable:
        return JSONResponse(status_code=202, content=_reply_classification_response(reply_id))
    except reply_workflow.ReplyClassificationError:
        return JSONResponse(status_code=502, content=_reply_classification_response(reply_id))
    return JSONResponse(status_code=200, content=result)


@app.get("/api/replies/{reply_id}/classification", tags=["replies"])
def api_get_reply_classification(reply_id: str) -> dict:
    return _reply_classification_response(reply_id)


@app.post("/api/prospects/{prospect_id}/score", status_code=202, tags=["prospects"])
def api_queue_prospect_score(prospect_id: int) -> dict:
    conn = db.connect()
    try:
        if db.get_prospect(conn, prospect_id) is None:
            raise HTTPException(status_code=404, detail="prospect not found")
        task_id = db.enqueue_task(conn, batch.SCORE_PROSPECT_TASK, {"prospect_id": prospect_id})
        return {"task_id": task_id, "status": "queued", "requires_ollama": False}
    finally:
        conn.close()


@app.post("/api/queue/retry", tags=["system"])
def api_retry_queue() -> dict:
    """Wake the local background worker to retry queued tasks immediately."""
    worker = getattr(app.state, "queue_worker", None)
    if worker is None:
        raise HTTPException(status_code=503, detail="queue worker is not running")
    worker.wake()
    conn = db.connect()
    try:
        return {"status": "scheduled", "queue": db.queue_counts(conn)}
    finally:
        conn.close()


@app.get("/health", tags=["system"])
def api_health() -> dict:
    """Check API/SQLite liveness without making local AI availability a prerequisite."""
    conn = None
    try:
        conn = db.connect()
        conn.execute("SELECT 1").fetchone()
    except (sqlite3.Error, OSError) as exc:
        logger.warning("health check failed: local SQLite is unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="local database unavailable") from exc
    finally:
        if conn is not None:
            conn.close()
    return {"status": "ok", "database": "ok", "ai_mode": "local-only"}


@app.get("/api/hardware", tags=["system"])
def api_hardware() -> dict:
    """Report detected RAM, CPU count, NVIDIA VRAM, tier, and model recommendation."""
    return hardware.detect().as_dict()


@app.get("/api/storage", tags=["system"])
def api_storage() -> dict:
    """Return local SQLite row, file-size, and embedded-vector metrics."""
    conn = db.connect()
    try:
        table_names = (
            "products", "prospects", "signal_runs", "signals", "emails",
            "sample_replies", "reply_classifications", "task_queue",
            "workflow_runs", "draft_runs",
        )
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in table_names
        }
        vector_columns = {
            "business_profiles": "embedding",
            "icps": "embedding",
            "prospects": "page_embedding",
            "prospect_research": "embedding",
        }
        vectors = {}
        for table, column in vector_columns.items():
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
            if column in columns:
                vectors[table] = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL"
                    ).fetchone()[0]
                )
        queue = db.queue_counts(conn)
    finally:
        conn.close()
    database_path = Path(db.get_db_path())
    file_bytes = 0
    for candidate in (database_path, Path(f"{database_path}-wal"), Path(f"{database_path}-shm")):
        try:
            file_bytes += candidate.stat().st_size
        except OSError:
            continue
    return {
        "engine": "SQLite",
        "mode": "local-only",
        "database_name": database_path.name,
        "file_bytes": file_bytes,
        "counts": counts,
        "vectors": vectors,
        "vector_rows": sum(vectors.values()),
        "queue": queue,
    }


@app.get("/api/status", tags=["system"])
def api_status() -> dict:
    """Return local Ollama availability and persistent queue status."""
    hw = hardware.detect()
    configured_model = os.environ.get("DEFAULT_MODEL", "").strip()
    conn = db.connect()
    try:
        queue = db.queue_counts(conn)
        latest_inference = db.latest_inference(conn)
    finally:
        conn.close()
    try:
        ollama_available = llm_client.ollama_up()
        ollama_state = "available" if ollama_available else "unavailable"
        ollama_message = None
        if ollama_available and _recent_timeout_inference(latest_inference):
            ollama_state = "slow"
            ollama_message = (
                "Ollama is reachable, but the last model request timed out; "
                "the model may be slow."
            )
    except llm_client.OllamaTimeout as exc:
        ollama_available = None
        ollama_state = "slow"
        ollama_message = f"Local Ollama is responding slowly; the model may still be loading. {exc}"
    except llm_client.OllamaResponseError as exc:
        ollama_available = False
        ollama_state = "error"
        ollama_message = str(exc)
    ollama = {
        "available": ollama_available,
        "state": ollama_state,
        "url": llm_client.OLLAMA_URL,
        "model": configured_model or hw.recommended_model,
        "last_inference": (
            {
                "task": latest_inference["task"],
                "model": latest_inference["model"],
                "status": latest_inference["status"],
                "temperature": latest_inference["temperature"],
                "seed": latest_inference["seed"],
                "repeat_penalty": latest_inference["repeat_penalty"],
                "prompt_hash": latest_inference["prompt_hash"],
                "commit_hash": latest_inference["commit_hash"],
                "created_at": latest_inference["created_at"],
            }
            if latest_inference
            else None
        ),
    }
    if ollama_message:
        ollama["message"] = ollama_message
    return {
        "service": "ok",
        "ai_mode": "local-only",
        "git_commit": GIT_COMMIT,
        "prompt_hashes": read_frozen_prompt_hashes(),
        "ollama": ollama,
        "hardware": hw.as_dict(),
        "queue": queue,
    }
