#!/usr/bin/env python3
"""Real local Ollama contract check for Phase 2; no mocks or cloud services.

Run from the repository root after installing Ollama and pulling the model:
    ollama pull qwen3:4b && python scripts/smoke_ollama.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from app import db
from app.llm_client import OLLAMA_URL, OllamaError, chat, ollama_version


class SmokeResponse(BaseModel):
    ok: bool
    message: str = Field(description="A short confirmation that local structured generation worked")


def print_ollama_list() -> None:
    print("$ ollama list")
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not run `ollama list`: {exc}") from exc
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"`ollama list` exited with status {result.returncode}")


def main() -> int:
    print(f"Ollama endpoint (fixed): {OLLAMA_URL}")
    print("GET /api/version")
    try:
        print(json.dumps(ollama_version(), indent=2, sort_keys=True))
        print_ollama_list()

        conn = db.connect()
        try:
            db.init_db(conn)
        finally:
            conn.close()

        raw = chat(
            'Reply with a JSON object whose "ok" value is true and whose "message" '
            'briefly confirms that local generation works.',
            model="qwen3:4b",
            task="phase2_smoke_test",
            format=SmokeResponse.model_json_schema(),
            system="Return only the requested JSON object.",
        )
        parsed = SmokeResponse.model_validate_json(raw)
        print("chat() response:")
        print(json.dumps(parsed.model_dump(), indent=2, sort_keys=True))

        conn = db.connect()
        try:
            row = db.latest_inference(conn)
            if row is None:
                raise RuntimeError("chat() returned but no inference_log row was written")
            print("latest inference_log row:")
            print(json.dumps(dict(row), indent=2, sort_keys=True))
        finally:
            conn.close()
        return 0
    except (OllamaError, RuntimeError, ValueError) as exc:
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
