#!/usr/bin/env python3
"""Live smoke test for the selected local Ollama model."""

from __future__ import annotations

import argparse
import json
import os
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
from app.text_clean import had_reasoning

EXPECTED_HOST = "http://127.0.0.1:11434"
EXPECTED_TAGS_URL = f"{EXPECTED_HOST}/api/tags"
EXPECTED_GENERATE_URL = f"{EXPECTED_HOST}/api/generate"
DEFAULT_MODEL = "qwen3:4b"


class SmokeFailure(RuntimeError):
    """Raised when a live-server acceptance check does not pass."""


def _selected_model() -> str:
    return os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


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


def _task_log(rows: list[dict], task_name: str) -> dict:
    for row in rows:
        if row["task"] == task_name:
            return row
    raise SmokeFailure(f"No inference-log row was written for {task_name}.")


def run_smoke() -> tuple[int, list[str]]:
    model = _selected_model()
    lines = [
        "Harvey Local Ollama live smoke test",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"endpoint: {OLLAMA_HOST}",
        f"model: {model}",
        f"ollama_executable: {shutil.which('ollama') or 'not found in sandbox PATH'}",
    ]
    try:
        _assert_local_endpoint()
    except SmokeFailure as exc:
        lines.extend(["status: FAIL", f"reason: {exc}"])
        return 1, lines

    with tempfile.TemporaryDirectory(prefix="harvey-ollama-smoke-") as temp_dir:
        db_path = Path(temp_dir) / "smoke.db"
        with OllamaClient(db_path=db_path, default_model=model, timeout=120.0) as client:
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
                        "hint: start Ollama and run 'ollama pull <DEFAULT_MODEL>', then rerun this script",
                    ]
                )
                return 2, lines

            try:
                cleaned_reply = client.generate(
                    task="smoke_think_false",
                    prompt='Reply with exactly the single word READY and no other text.',
                    model=model,
                )
                raw_reply = client.last_raw_response
                if raw_reply is None:
                    raise SmokeFailure("The client did not retain the raw reply for the smoke check.")
                reasoning_in_reply = had_reasoning(raw_reply)
                reasoning_emitted = reasoning_in_reply or client.last_response_had_thinking is True
                lines.append(
                    f"INFO model emitted reasoning: {'yes' if reasoning_emitted else 'no'}"
                )

                think_request = client.last_request_metadata or {}
                if think_request.get("url") != EXPECTED_GENERATE_URL:
                    raise SmokeFailure("The text request did not use the fixed local URL.")
                if think_request.get("think") is not False:
                    raise SmokeFailure("The text request did not send think=false.")
                if think_request.get("num_predict") != 1500:
                    raise SmokeFailure("The default num_predict was not 1500.")

                text_log = _task_log(
                    list_inference_logs(limit=10, db_path=db_path), "smoke_think_false"
                )
                latency = text_log["latency_seconds"]
                tokens_per_second = text_log["tokens_per_second"]
                if text_log["model"] != model or text_log["host"] != EXPECTED_HOST:
                    raise SmokeFailure("The inference log has an unexpected model or host.")
                if text_log["eval_tokens"] is None:
                    raise SmokeFailure("eval_count was not recorded in inference_log.")
                if latency is None or latency < 0:
                    raise SmokeFailure("Latency was not recorded in inference_log.")
                if tokens_per_second is None or tokens_per_second < 0:
                    raise SmokeFailure("Tokens per second were not recorded in inference_log.")

                if cleaned_reply == "READY":
                    lines.append(
                        "PASS cleaned output equals READY; "
                        f"latency={latency:.6f}s tokens_per_second={tokens_per_second:.3f}"
                    )
                else:
                    lines.append(
                        "FAIL cleaned output does not equal READY; "
                        f"actual={cleaned_reply!r} latency={latency:.6f}s "
                        f"tokens_per_second={tokens_per_second:.3f}"
                    )
                    raise SmokeFailure("Cleaned text response was not exactly READY.")

                json_text = client.generate(
                    task="smoke_json_format",
                    prompt='Return exactly this JSON object and no prose: {"status":"ok","count":3}',
                    model=model,
                    response_format="json",
                )
                lines.append(f"format_json_response: {json_text!r}")
                json_request = client.last_request_metadata or {}
                if json_request.get("url") != EXPECTED_GENERATE_URL:
                    raise SmokeFailure("The JSON request did not use the fixed local URL.")
                if json_request.get("format") != "json":
                    raise SmokeFailure('The JSON request did not send format="json".')
                parsed = json.loads(json_text)
                if not isinstance(parsed, dict) or parsed.get("status") != "ok":
                    raise SmokeFailure(f"Unexpected JSON object: {parsed!r}")
                lines.append("format_json: PASS (response parsed as a JSON object)")

                rows = list_inference_logs(limit=10, db_path=db_path)
                json_log = _task_log(rows, "smoke_json_format")
                for task_name, row in (("smoke_think_false", text_log), ("smoke_json_format", json_log)):
                    if row["host"] != EXPECTED_HOST or row["model"] != model:
                        raise SmokeFailure(f"Unexpected host or model in {task_name} log.")
                    if row["prompt_tokens"] is None or row["eval_tokens"] is None:
                        raise SmokeFailure(f"Token counts are missing in {task_name} log.")
                    if row["latency_seconds"] is None or row["tokens_per_second"] is None:
                        raise SmokeFailure(f"Latency or throughput is missing in {task_name} log.")
                    if row["status"] != "success":
                        raise SmokeFailure(f"Inference log is not successful for {task_name}.")
                    lines.append(
                        f"log[{task_name}]: host={row['host']} model={row['model']} "
                        f"prompt_tokens={row['prompt_tokens']} eval_count={row['eval_tokens']} "
                        f"latency_seconds={row['latency_seconds']:.6f} "
                        f"tokens_per_second={row['tokens_per_second']:.3f}"
                    )

                peers = _process_tcp_peers()
                if peers is None:
                    lines.append("observed_tcp_peers: unavailable (actual request URLs checked)")
                else:
                    unexpected = [peer for peer in peers if peer != "127.0.0.1:11434"]
                    lines.append(f"observed_tcp_peers: {peers or 'none at sample time'}")
                    if unexpected:
                        raise SmokeFailure(f"Unexpected TCP peer(s): {unexpected}")
                lines.append("network_target: PASS (health and generation URLs use only 127.0.0.1:11434)")
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
