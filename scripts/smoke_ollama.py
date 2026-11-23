#!/usr/bin/env python3
"""Local Ollama contract check for Phase 2; no test doubles or cloud services.

Run from the repository root after installing Ollama and pulling the model:
    ollama pull qwen3:4b && python scripts/smoke_ollama.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from app import db, hardware
from app.llm_client import OLLAMA_URL, OllamaError, chat, ollama_version


class SmokeDetails(BaseModel):
    message: str = Field(description="A short confirmation that local structured generation worked")


class SmokeResponse(BaseModel):
    status: Literal["ok"]
    details: SmokeDetails


def print_ollama_list() -> None:
    print("$ ollama list")
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=30, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Ollama CLI was not found. Install Ollama and ensure `ollama` is on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("`ollama list` timed out after 30 seconds") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run `ollama list`: {exc}") from exc
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"`ollama list` exited with status {result.returncode}")


def _mark_smoke_schema_error() -> None:
    """Best-effort update when JSON is valid but fails the nested Pydantic schema."""
    conn = None
    try:
        conn = db.connect()
        row = db.latest_inference(conn)
        if row is not None and row["task"] == "phase2_smoke_test":
            db.update_inference_status(conn, row["id"], "error:invalid_json")
    except Exception as exc:
        print(f"Could not update smoke inference status: {exc}", file=sys.stderr)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:
                print(f"Could not close smoke status database connection: {exc}", file=sys.stderr)


def main() -> int:
    print(f"Ollama endpoint (fixed): {OLLAMA_URL}")
    try:
        print_ollama_list()
        print("GET /api/version")
        print(json.dumps(ollama_version(), indent=2, sort_keys=True))

        conn = db.connect()
        try:
            db.init_db(conn)
        finally:
            conn.close()

        num_ctx = hardware.detect().recommended_num_ctx
        print(f"Using hardware-tier num_ctx: {num_ctx}")
        raw = chat(
            'Return a JSON object with status "ok" and a nested details object whose '
            'message briefly confirms that local generation works.',
            model="qwen3:4b",
            task="phase2_smoke_test",
            format=SmokeResponse.model_json_schema(),
            system="Return only the requested JSON object matching the supplied schema.",
            num_ctx=num_ctx,
        )
        print("chat() content (after <think> stripping):")
        print(raw)
        try:
            parsed = SmokeResponse.model_validate_json(raw)
        except ValueError as exc:
            _mark_smoke_schema_error()
            print(f"Nested schema validation failed: {exc}", file=sys.stderr)
            parsed = None
        if parsed is not None:
            print("validated nested response:")
            print(json.dumps(parsed.model_dump(), indent=2, sort_keys=True))

        conn = db.connect()
        try:
            row = db.latest_inference(conn)
            if row is None or row["task"] != "phase2_smoke_test":
                raise RuntimeError("chat() returned but no smoke inference_log row was written")
            print("smoke inference_log row:")
            print(json.dumps(dict(row), indent=2, sort_keys=True))
            if row["status"] != "ok":
                print(f"Unexpected inference status: {row['status']}", file=sys.stderr)
                return 1
        finally:
            conn.close()
        return 0 if parsed is not None else 1
    except (OllamaError, RuntimeError, ValueError) as exc:
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
