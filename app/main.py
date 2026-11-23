"""FastAPI entry point for the local Harvey service."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app import db, hardware, llm_client
from app.queue_worker import QueueWorker


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    conn = db.connect()
    try:
        db.init_db(conn)
    finally:
        conn.close()

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


@app.get("/api/hardware", tags=["system"])
def api_hardware() -> dict:
    """Report detected RAM, CPU count, NVIDIA VRAM, tier, and model recommendation."""
    return hardware.detect().as_dict()


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
        if ollama_available and latest_inference and latest_inference["status"] == "error:timeout":
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
                "status": latest_inference["status"],
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
        "ollama": ollama,
        "hardware": hw.as_dict(),
        "queue": queue,
    }
