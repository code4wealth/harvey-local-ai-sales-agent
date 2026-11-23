#!/usr/bin/env python3
"""Run one profile or ICP workflow against the local Ollama instance."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.llm_client import OllamaUnavailable  # noqa: E402
from app.workflows import common, icp, profile  # noqa: E402


def _metrics(task: str) -> tuple[int, float]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT eval_tokens, seconds FROM inference_log WHERE task = ? ORDER BY id",
            (task,),
        ).fetchall()
        eval_count = sum(int(row["eval_tokens"]) for row in rows)
        model_seconds = sum(float(row["seconds"]) for row in rows)
        return eval_count, model_seconds
    finally:
        conn.close()


def _read_run(run_id: int) -> dict[str, Any]:
    return common.read_run_payload(run_id)


def _write_evidence(payload: dict[str, Any]) -> Path:
    evidence_dir = ROOT / "test_evidence" / "real_run"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = evidence_dir / f"{payload['workflow']}_{payload['product_id']}_{timestamp}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow", choices=("profile", "icp"))
    parser.add_argument("product_id", type=int)
    args = parser.parse_args(argv)

    conn = db.connect()
    try:
        db.init_db(conn)
    finally:
        conn.close()

    submit = profile.submit_profile if args.workflow == "profile" else icp.submit_icp
    started = time.perf_counter()
    run_id: int | None = None
    raised_error: str | None = None
    try:
        run_id = submit(args.product_id)
    except OllamaUnavailable as exc:
        run_id = getattr(exc, "workflow_run_id", None)
        raised_error = f"{type(exc).__name__}: {exc}"
    except common.WorkflowRunError as exc:
        run_id = exc.run_id
        raised_error = f"{type(exc).__name__}: {exc}"
    except common.ProductNotFound as exc:
        print(f"product error: {exc}", file=sys.stderr)
        return 2

    latency_seconds = time.perf_counter() - started
    if run_id is None:
        print(raised_error or "workflow failed before a run was recorded", file=sys.stderr)
        return 1

    try:
        run = _read_run(int(run_id))
    except (OSError, ValueError) as exc:
        print(f"could not read the stored workflow run: {exc}", file=sys.stderr)
        return 1

    task = f"{args.workflow}:{run_id}"
    eval_count, model_seconds = _metrics(task)
    tokens_per_second = eval_count / model_seconds if model_seconds > 0 else None
    evidence: dict[str, Any] = {
        "workflow": args.workflow,
        "product_id": args.product_id,
        "run_id": int(run_id),
        "status": run["status"],
        "queue_task_id": run["queue_task_id"],
        "model_name": run["model_name"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "error": run["error"] or raised_error,
        "metrics": {
            "eval_count": eval_count,
            "tokens_per_second": tokens_per_second,
            "latency_seconds": latency_seconds,
            "model_seconds": model_seconds,
        },
    }
    if run["status"] == "succeeded":
        evidence["output"] = run["result"]

    print(f"workflow: {args.workflow}")
    print(f"product_id: {args.product_id}")
    print(f"status: {run['status']}")
    print(f"model: {run['model_name'] or 'not resolved'}")
    if run["status"] == "succeeded":
        print("output:")
        print(json.dumps(run["result"], ensure_ascii=False, indent=2))
    else:
        print(f"failure/status detail: {evidence['error'] or run['status']}")
    print(f"eval_count: {eval_count}")
    rate_text = f"{tokens_per_second:.2f}" if tokens_per_second is not None else "n/a"
    print(f"tokens_per_second: {rate_text}")
    print(f"latency_seconds: {latency_seconds:.3f}")

    path = _write_evidence(evidence)
    print(f"evidence: {path.relative_to(ROOT)}")
    return 0 if run["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
