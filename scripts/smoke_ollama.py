#!/usr/bin/env python3
"""Live smoke test for the real local qwen3:4b Ollama endpoint."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psutil

from app.db import list_inference_logs
from app.llm_client import OLLAMA_GENERATE_URL, OLLAMA_HOST, OllamaClient

EXPECTED_HOST = "http://127.0.0.1:11434"
EXPECTED_TAGS_URL = f"{EXPECTED_HOST}/api/tags"
EXPECTED_GENERATE_URL = f"{EXPECTED_HOST}/api/generate"
MODEL = "qwen3:4b"


class SmokeFailure(RuntimeError):
    """Raised when a live-server acceptance check does not pass."""


def _process_tcp_peers() -> list[str] | None:
    """Return this process's connected TCP peers, or None if not observable."""
    try:
        connections = psutil.Process().net_connections(kind="tcp")
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return None
    peers = []
    for connection in connections:
        if not connection.raddr:
            continue
        address = connection.raddr
        peers.append(f"{address.ip}:{address.port}")
    return sorted(set(peers))


def _assert_local_endpoint() -> None:
    parsed_host = urlsplit(OLLAMA_HOST)
    parsed_generate = urlsplit(OLLAMA_GENERATE_URL)
    if (
        OLLAMA_HOST != EXPECTED_HOST
        or parsed_host.hostname != "127.0.0.1"
        or parsed_host.port != 11434
        or parsed_generate.hostname != "127.0.0.1"
        or parsed_generate.port != 11434
        or OLLAMA_GENERATE_URL != EXPECTED_GENERATE_URL
    ):
        raise SmokeFailure(
            f"Client endpoint is not the required local address: {OLLAMA_HOST}"
        )


def run_smoke() -> tuple[int, list[str]]:
    lines = [
        "Harvey Local Ollama live smoke test",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"endpoint: {OLLAMA_HOST}",
        f"model: {MODEL}",
        f"ollama_executable: {shutil.which('ollama') or 'not found in sandbox PATH'}",
    ]
    try:
        _assert_local_endpoint()
    except SmokeFailure as exc:
        lines.extend(["status: FAIL", f"reason: {exc}"])
        return 1, lines

    with tempfile.TemporaryDirectory(prefix="harvey-ollama-smoke-") as temp_dir:
        db_path = Path(temp_dir) / "smoke.db"
        with OllamaClient(db_path=db_path, default_model=MODEL, timeout=120.0) as client:
            server_available = client.ollama_up()
            health_url = client.last_health_url
            lines.append(f"health_check_url: {health_url}")
            if health_url != EXPECTED_TAGS_URL:
                lines.extend(["status: FAIL", "reason: health request URL was not local Ollama"])
                return 1, lines
            if not server_available:
                try:
                    httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2.0)
                    detail = "local tags endpoint did not return a successful status"
                except httpx.HTTPError as exc:
                    detail = f"{type(exc).__name__}: {exc}"
                lines.extend(
                    [
                        "status: BLOCKED",
                        "live_inference: not attempted",
                        f"health_check: {detail}",
                        "hint: start Ollama in this environment and run 'ollama pull qwen3:4b', then rerun this script",
                    ]
                )
                return 2, lines

            try:
                plain_text = client.generate(
                    task="smoke_think_false",
                    prompt="Reply with exactly the single word READY and no other text.",
                    model=MODEL,
                )
                lines.append(f"think_false_response: {plain_text!r}")
                think_request = client.last_request_metadata or {}
                if think_request.get("url") != OLLAMA_GENERATE_URL:
                    raise SmokeFailure("The text request did not use the fixed local URL.")
                if think_request.get("think") is not False:
                    raise SmokeFailure("The text request did not send think=false.")
                if client.last_response_had_thinking is not False:
                    raise SmokeFailure(
                        "The raw response contained a think tag or could not be inspected."
                    )
                if "<think" in plain_text.lower() or "</think" in plain_text.lower():
                    raise SmokeFailure("The text returned by the client contains a think tag.")
                lines.append("think_false: PASS (request flag false; raw output had no think tags)")

                json_text = client.generate(
                    task="smoke_json_format",
                    prompt=(
                        'Return exactly this JSON object and no prose: '
                        '{"status":"ok","count":3}'
                    ),
                    model=MODEL,
                    response_format="json",
                )
                lines.append(f"format_json_response: {json_text!r}")
                json_request = client.last_request_metadata or {}
                if json_request.get("format") != "json":
                    raise SmokeFailure('The JSON request did not send format="json".')
                parsed = json.loads(json_text)
                if not isinstance(parsed, dict) or parsed.get("status") != "ok":
                    raise SmokeFailure(f"Unexpected JSON object: {parsed!r}")
                lines.append("format_json: PASS (response parsed as a JSON object)")

                rows = list_inference_logs(limit=10, db_path=db_path)
                relevant = {
                    row["task"]: row
                    for row in rows
                    if row["task"] in {"smoke_think_false", "smoke_json_format"}
                }
                if set(relevant) != {"smoke_think_false", "smoke_json_format"}:
                    raise SmokeFailure("Expected inference-log rows were not written.")
                for task_name, row in relevant.items():
                    if row["host"] != EXPECTED_HOST:
                        raise SmokeFailure(f"Unexpected inference-log host for {task_name}.")
                    if row["model"] != MODEL:
                        raise SmokeFailure(f"Unexpected inference-log model for {task_name}.")
                    if row["prompt_tokens"] is None or row["eval_tokens"] is None:
                        raise SmokeFailure(
                            f"Token counts were missing from the response for {task_name}."
                        )
                    if row["prompt_tokens"] < 0 or row["eval_tokens"] < 0:
                        raise SmokeFailure(f"Invalid token counts for {task_name}.")
                    if row["latency_seconds"] is None or row["latency_seconds"] < 0:
                        raise SmokeFailure(f"Latency was not logged for {task_name}.")
                    if row["status"] != "success":
                        raise SmokeFailure(f"Inference log is not successful for {task_name}.")
                lines.append("inference_log: PASS (2 rows; model, local host, tokens, latency present)")
                lines.append(
                    f"generation_urls: {think_request['url']}, {json_request['url']}"
                )
                for task_name in ("smoke_think_false", "smoke_json_format"):
                    row = relevant[task_name]
                    lines.append(
                        f"log[{task_name}]: host={row['host']} model={row['model']} "
                        f"prompt_tokens={row['prompt_tokens']} eval_tokens={row['eval_tokens']} "
                        f"latency_seconds={row['latency_seconds']:.6f} status={row['status']}"
                    )

                peers = _process_tcp_peers()
                if peers is None:
                    lines.append("observed_tcp_peers: unavailable (static client URL checked)")
                else:
                    unexpected = [peer for peer in peers if peer != "127.0.0.1:11434"]
                    lines.append(f"observed_tcp_peers: {peers or 'none at sample time'}")
                    if unexpected:
                        raise SmokeFailure(f"Unexpected TCP peer(s): {unexpected}")
                lines.append(
                    "network_target: PASS (observed health and generation request URLs all use 127.0.0.1:11434)"
                )
            except Exception as exc:
                lines.extend(["status: FAIL", f"reason: {type(exc).__name__}: {exc}"])
                return 1, lines

    lines.append("status: PASS")
    return 0, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test_evidence/smoke_ollama.txt"),
        help="Path for the smoke-test transcript.",
    )
    args = parser.parse_args()
    exit_code, lines = run_smoke()
    transcript = "\n".join(lines) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(transcript, encoding="utf-8")
    sys.stdout.write(transcript)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
