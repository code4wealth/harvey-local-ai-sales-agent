"""Persistent product-level orchestration for the local sales workflow."""

from __future__ import annotations

import json
import logging
from typing import Any

from app import db, llm_client
from app.queue_worker import register_handler
from app.workflows import common
from app.workflows import draft as draft_workflow
from app.workflows import icp as icp_workflow
from app.workflows import problem_statement as problem_workflow
from app.workflows import profile as profile_workflow
from app.workflows import ranking as ranking_workflow
from app.workflows import signals as signal_workflow

logger = logging.getLogger("harvey.pipeline")
TASK_TYPE = "workflow.pipeline"
DEFAULT_PROSPECT_LIMIT = 3
_TERMINAL_STEP_STATUSES = {"done", "failed", "skipped"}


class PipelineProductNotFound(LookupError):
    """The requested pipeline product does not exist."""


class PipelineQueueError(RuntimeError):
    """A pipeline run was stored but its queue task could not be created."""


def _step_specs(prospects: list[Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"step_name": "profile", "step_order": 0},
        {"step_name": "icp", "step_order": 1},
    ]
    order = 2
    for prospect in prospects:
        prospect_id = int(prospect["id"])
        for step_name in ("signals", "problem_statement", "draft"):
            steps.append(
                {
                    "step_name": f"{step_name}:{prospect_id}",
                    "step_order": order,
                    "prospect_id": prospect_id,
                }
            )
            order += 1
    steps.append({"step_name": "ranking", "step_order": order})
    return steps


def _step_label(row) -> str:
    name = str(row["step_name"])
    base = name.split(":", 1)[0]
    labels = {
        "profile": "Business profile",
        "icp": "Ideal customer profile",
        "signals": "Signals and research",
        "problem_statement": "Problem statement",
        "draft": "Unsent outreach draft",
        "ranking": "Prospect ranking",
    }
    label = labels.get(base, base.replace("_", " ").title())
    if row["prospect_id"] is not None:
        company = str(row["prospect_name"] or "").strip() or f"Prospect {row['prospect_id']}"
        return f"{label} · {company}"
    return label


def _decode_result(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return result if isinstance(result, dict) else {}


def pipeline_run_payload(conn, row) -> dict[str, Any]:
    if row is None:
        raise ValueError("pipeline run not found")
    steps = []
    for step in db.list_pipeline_steps(conn, int(row["id"])):
        steps.append(
            {
                "id": int(step["id"]),
                "step_name": step["step_name"],
                "step_order": int(step["step_order"]),
                "prospect_id": int(step["prospect_id"]) if step["prospect_id"] is not None else None,
                "prospect_name": step["prospect_name"],
                "label": _step_label(step),
                "status": step["status"],
                "error": step["last_error"],
                "result": _decode_result(step["result_json"]),
                "started_at": step["started_at"],
                "finished_at": step["finished_at"],
            }
        )
    counts = {status: 0 for status in ("queued", "running", "done", "failed", "skipped")}
    for step in steps:
        counts[step["status"]] = counts.get(step["status"], 0) + 1
    failed_step = next((step for step in steps if step["status"] == "failed"), None)
    prospect_ids = {
        step["prospect_id"] for step in steps if step["prospect_id"] is not None
    }
    prospect_limit = row["prospect_limit"]
    prospect_count = row["prospect_count"]
    return {
        "pipeline": True,
        "id": int(row["id"]),
        "product_id": int(row["product_id"]),
        "prospect_limit": int(prospect_limit) if prospect_limit is not None else None,
        "prospect_count": (
            int(prospect_count) if prospect_count is not None else len(prospect_ids)
        ),
        "status": row["status"],
        "model_name": row["model_name"],
        "queue_task_id": row["queue_task_id"],
        "error": failed_step["error"] if failed_step else None,
        "step_counts": counts,
        "steps": steps,
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def read_pipeline_run_payload(run_id: int) -> dict[str, Any]:
    conn = db.connect()
    try:
        row = db.get_pipeline_run(conn, run_id)
        if row is None:
            raise ValueError(f"pipeline run {run_id} not found")
        return pipeline_run_payload(conn, row)
    finally:
        conn.close()


def latest_pipeline_payload(product_id: int) -> dict[str, Any]:
    conn = db.connect()
    try:
        if db.get_product(conn, product_id) is None:
            raise PipelineProductNotFound(f"product {product_id} not found")
        row = db.latest_pipeline_run(conn, product_id)
        if row is None:
            raise LookupError(f"no pipeline run is stored for product {product_id}")
        return pipeline_run_payload(conn, row)
    finally:
        conn.close()


def submit_pipeline(
    product_id: int,
    *,
    model: str | None = None,
    prospect_limit: int = DEFAULT_PROSPECT_LIMIT,
) -> dict[str, Any]:
    """Snapshot a bounded prospect set and enqueue one full local run."""
    if (
        isinstance(prospect_limit, bool)
        or not isinstance(prospect_limit, int)
        or prospect_limit < 1
    ):
        raise ValueError("prospect_limit must be a positive integer")
    model_name = llm_client.resolve_model_name(model)
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        product = db.get_product(conn, product_id)
        if product is None:
            raise PipelineProductNotFound(f"product {product_id} not found")
        active = conn.execute(
            "SELECT * FROM pipeline_runs WHERE product_id = ? "
            "AND status IN ('queued', 'running') ORDER BY id DESC LIMIT 1",
            (int(product_id),),
        ).fetchone()
        if active is not None:
            return pipeline_run_payload(conn, active)

        prospects = db.list_prospects(conn, product_id)[:prospect_limit]
        run_id = db.create_pipeline_run(
            conn,
            product_id=product_id,
            model_name=model_name,
            prospect_limit=prospect_limit,
            prospect_count=len(prospects),
            steps=_step_specs(prospects),
        )
        try:
            task_id = db.enqueue_task(
                conn,
                TASK_TYPE,
                {
                    "pipeline_run_id": run_id,
                    "product_id": int(product_id),
                    "model_name": model_name,
                    "prospect_limit": prospect_limit,
                },
            )
            db.update_pipeline_run(
                conn,
                run_id,
                status="queued",
                model_name=model_name,
                queue_task_id=task_id,
            )
        except Exception as exc:
            db.update_pipeline_run(conn, run_id, status="failed", model_name=model_name)
            for step in db.list_pipeline_steps(conn, run_id):
                db.update_pipeline_step(
                    conn,
                    int(step["id"]),
                    status="failed",
                    last_error=f"could not queue pipeline: {type(exc).__name__}: {exc}",
                )
            raise PipelineQueueError("could not queue the product pipeline") from exc
        row = db.get_pipeline_run(conn, run_id)
        return pipeline_run_payload(conn, row)
    finally:
        conn.close()


def _step_details(step) -> dict[str, Any]:
    return _decode_result(step["result_json"])


def _save_step_details(step_id: int, details: dict[str, Any]) -> None:
    conn = db.connect()
    try:
        db.update_pipeline_step(
            conn,
            step_id,
            status="running",
            result=details,
        )
    finally:
        conn.close()


def _workflow_run_id(step, *, key: str, product_id: int, workflow: str, model_name: str) -> int:
    details = _step_details(step)
    run_id = details.get(key)
    if run_id is not None:
        run_id = int(run_id)
        conn = db.connect()
        try:
            row = db.get_workflow_run(conn, run_id)
            if (
                row is None
                or int(row["product_id"]) != int(product_id)
                or row["workflow"] != workflow
            ):
                raise ValueError(f"stored {workflow} run does not match its pipeline step")
            if row["status"] == "succeeded":
                return run_id
            if row["status"] == "failed":
                raise RuntimeError(row["error"] or f"{workflow} workflow failed")
            return run_id
        finally:
            conn.close()

    run_id = common.create_run(
        product_id,
        workflow,
        model_name,
        temperature=llm_client.DEFAULT_TEMPERATURE,
        seed=llm_client.DEFAULT_SEED,
        repeat_penalty=llm_client.DEFAULT_REPEAT_PENALTY,
    )
    details[key] = run_id
    _save_step_details(int(step["id"]), details)
    return run_id


def _run_profile_or_icp(step, *, product_id: int, model_name: str, workflow: str) -> dict[str, Any]:
    key = f"{workflow}_run_id"
    run_id = _workflow_run_id(
        step, key=key, product_id=product_id, workflow=workflow, model_name=model_name
    )
    conn = db.connect()
    try:
        run = db.get_workflow_run(conn, run_id)
        if run is not None and run["status"] == "succeeded":
            return {key: run_id}
    finally:
        conn.close()

    try:
        if workflow == "profile":
            profile_workflow.execute_profile_run(product_id, run_id, model_name)
        else:
            icp_workflow.execute_icp_run(product_id, run_id, model_name)
    except llm_client.OllamaUnavailable as exc:
        common.update_run(run_id, status="queued", error=f"{type(exc).__name__}: {exc}", model_name=model_name)
        raise
    except Exception as exc:
        common.set_run_failure(run_id, f"{type(exc).__name__}: {exc}", model_name)
        raise
    return {key: run_id}


def _signal_run_id(step, *, product_id: int, prospect_id: int, model_name: str) -> int:
    details = _step_details(step)
    run_id = details.get("signal_run_id")
    if run_id is not None:
        run_id = int(run_id)
        conn = db.connect()
        try:
            row = db.get_signal_run(conn, run_id)
            if (
                row is None
                or int(row["product_id"]) != int(product_id)
                or int(row["prospect_id"]) != int(prospect_id)
            ):
                raise ValueError("stored signal run does not match its pipeline step")
            if row["status"] == "succeeded":
                return run_id
            if row["status"] == "failed":
                raise RuntimeError(row["error"] or "signal extraction failed")
            return run_id
        finally:
            conn.close()

    conn = db.connect()
    try:
        run_id = db.create_signal_run(
            conn,
            prospect_id=prospect_id,
            model_name=model_name,
            temperature=llm_client.DEFAULT_TEMPERATURE,
            seed=llm_client.DEFAULT_SEED,
            repeat_penalty=llm_client.DEFAULT_REPEAT_PENALTY,
        )
    finally:
        conn.close()
    details["signal_run_id"] = run_id
    _save_step_details(int(step["id"]), details)
    return run_id


def _run_signals(step, *, product_id: int, prospect_id: int, model_name: str) -> dict[str, Any]:
    run_id = _signal_run_id(
        step,
        product_id=product_id,
        prospect_id=prospect_id,
        model_name=model_name,
    )
    conn = db.connect()
    try:
        row = db.get_signal_run(conn, run_id)
        if row is not None and row["status"] == "succeeded":
            return {"signal_run_id": run_id, "signal_count": len(json.loads(row["signals_json"] or "[]"))}
    finally:
        conn.close()

    try:
        signal_workflow.execute_signal_run(prospect_id, run_id, model_name)
    except llm_client.OllamaUnavailable as exc:
        conn = db.connect()
        try:
            db.update_signal_run(
                conn,
                run_id,
                status="queued",
                error=f"{type(exc).__name__}: {exc}",
                model_name=model_name,
            )
        finally:
            conn.close()
        raise
    except Exception as exc:
        conn = db.connect()
        try:
            db.update_signal_run(
                conn,
                run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                model_name=model_name,
            )
        finally:
            conn.close()
        raise
    conn = db.connect()
    try:
        row = db.get_signal_run(conn, run_id)
        return {"signal_run_id": run_id, "signal_count": len(json.loads(row["signals_json"] or "[]"))}
    finally:
        conn.close()


def _problem_run_id(step, *, product_id: int, prospect_id: int, model_name: str) -> int:
    details = _step_details(step)
    run_id = details.get("problem_statement_id")
    if run_id is not None:
        run_id = int(run_id)
        conn = db.connect()
        try:
            row = db.get_problem_statement_run(conn, run_id)
            if (
                row is None
                or int(row["product_id"]) != int(product_id)
                or int(row["prospect_id"]) != int(prospect_id)
            ):
                raise ValueError("stored problem statement does not match its pipeline step")
            if row["status"] in {"succeeded", "skipped"}:
                return run_id
            if row["status"] == "failed":
                raise RuntimeError(row["error"] or "problem statement failed")
            return run_id
        finally:
            conn.close()

    profile_id, icp_id, signal_run_id, verified, source_ids = problem_workflow._latest_sources(
        product_id, prospect_id
    )
    conn = db.connect()
    try:
        run_id = db.create_problem_statement_run(
            conn,
            product_id=product_id,
            prospect_id=prospect_id,
            business_profile_id=profile_id,
            icp_id=icp_id,
            signal_run_id=signal_run_id,
            source_signal_ids=source_ids,
            model_name=model_name if verified else None,
            temperature=llm_client.DEFAULT_TEMPERATURE,
            seed=llm_client.DEFAULT_SEED,
            repeat_penalty=llm_client.DEFAULT_REPEAT_PENALTY,
        )
        if not verified:
            db.update_problem_statement_run(
                conn, run_id, status="skipped", error=problem_workflow.NO_EVIDENCE
            )
    finally:
        conn.close()
    details["problem_statement_id"] = run_id
    _save_step_details(int(step["id"]), details)
    return run_id


def _run_problem_statement(
    step, *, product_id: int, prospect_id: int, model_name: str
) -> dict[str, Any]:
    run_id = _problem_run_id(
        step, product_id=product_id, prospect_id=prospect_id, model_name=model_name
    )
    conn = db.connect()
    try:
        row = db.get_problem_statement_run(conn, run_id)
        if row is not None and row["status"] in {"succeeded", "skipped"}:
            return {"problem_statement_id": run_id, "status": row["status"], "reason": row["error"]}
    finally:
        conn.close()
    try:
        problem_workflow.execute_problem_statement_run(run_id, model_name)
    except llm_client.OllamaUnavailable as exc:
        conn = db.connect()
        try:
            db.update_problem_statement_run(
                conn,
                run_id,
                status="queued",
                error=f"{type(exc).__name__}: {exc}",
                model_name=model_name,
            )
        finally:
            conn.close()
        raise
    except Exception as exc:
        conn = db.connect()
        try:
            db.update_problem_statement_run(
                conn,
                run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                model_name=model_name,
            )
        finally:
            conn.close()
        raise
    return {"problem_statement_id": run_id, "status": "succeeded"}


def _draft_run_id(step, *, product_id: int, prospect_id: int, model_name: str) -> int:
    details = _step_details(step)
    run_id = details.get("draft_run_id")
    if run_id is not None:
        run_id = int(run_id)
        conn = db.connect()
        try:
            row = db.get_draft_run(conn, run_id)
            if (
                row is None
                or int(row["product_id"]) != int(product_id)
                or int(row["prospect_id"]) != int(prospect_id)
            ):
                raise ValueError("stored draft does not match its pipeline step")
            if row["status"] in {"succeeded", "skipped"}:
                return run_id
            if row["status"] == "failed":
                raise RuntimeError(row["error"] or "draft generation failed")
            return run_id
        finally:
            conn.close()

    profile_id, signal_run_id, verified, evidence_reason = draft_workflow._latest_sources(
        product_id, prospect_id
    )
    conn = db.connect()
    try:
        run_id = db.create_draft_run(
            conn,
            product_id=product_id,
            prospect_id=prospect_id,
            business_profile_id=profile_id,
            signal_run_id=signal_run_id,
            model_name=model_name if verified else None,
            temperature=llm_client.DEFAULT_TEMPERATURE,
            seed=llm_client.DEFAULT_SEED,
            repeat_penalty=llm_client.DEFAULT_REPEAT_PENALTY,
        )
        if not verified:
            db.update_draft_run(
                conn,
                run_id,
                status="skipped",
                error=evidence_reason or draft_workflow.NO_EVIDENCE,
            )
    finally:
        conn.close()
    details["draft_run_id"] = run_id
    _save_step_details(int(step["id"]), details)
    return run_id


def _run_draft(step, *, product_id: int, prospect_id: int, model_name: str) -> dict[str, Any]:
    run_id = _draft_run_id(step, product_id=product_id, prospect_id=prospect_id, model_name=model_name)
    conn = db.connect()
    try:
        row = db.get_draft_run(conn, run_id)
        if row is not None and row["status"] in {"succeeded", "skipped"}:
            return {"draft_run_id": run_id, "status": row["status"], "reason": row["error"]}
    finally:
        conn.close()
    try:
        draft_workflow.execute_draft_run(run_id, model_name)
    except llm_client.OllamaUnavailable as exc:
        conn = db.connect()
        try:
            db.update_draft_run(
                conn,
                run_id,
                status="queued",
                error=f"{type(exc).__name__}: {exc}",
                model_name=model_name,
            )
        finally:
            conn.close()
        raise
    except Exception as exc:
        conn = db.connect()
        try:
            db.update_draft_run(
                conn,
                run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                model_name=model_name,
            )
        finally:
            conn.close()
        raise
    return {"draft_run_id": run_id, "status": "succeeded"}


def _step_status(run_id: int, step_name: str) -> str | None:
    conn = db.connect()
    try:
        row = db.get_pipeline_step(conn, run_id, step_name)
        return str(row["status"]) if row is not None else None
    finally:
        conn.close()


def _critical_step_failure_reason(run_id: int) -> str | None:
    """Return a skip reason when a required product-level gate has failed."""
    conn = db.connect()
    try:
        for step_name, label in (("profile", "business profile"), ("icp", "ICP")):
            row = db.get_pipeline_step(conn, run_id, step_name)
            if row is None or row["status"] != "failed":
                continue
            error = str(row["last_error"] or "").strip()
            if error:
                return f"Skipped because the {label} step failed: {error}"
            return f"Skipped because the {label} step failed."
    finally:
        conn.close()
    return None


def _skip_dependency(step_name: str, run_id: int) -> str | None:
    base, _, suffix = step_name.partition(":")
    prospect_id = int(suffix) if suffix else None
    if base == "icp" and _step_status(run_id, "profile") != "done":
        return "Skipped because the business profile did not succeed."
    if base == "problem_statement":
        if _step_status(run_id, "profile") != "done" or _step_status(run_id, "icp") != "done":
            return "Skipped because the business profile and ICP are required."
        if prospect_id is not None and _step_status(run_id, f"signals:{prospect_id}") != "done":
            return "Skipped because prospect signals did not complete."
    if base == "draft":
        if _step_status(run_id, "profile") != "done":
            return "Skipped because the business profile is required."
        if prospect_id is not None and _step_status(run_id, f"signals:{prospect_id}") != "done":
            return "Skipped because prospect signals did not complete."
    return None


def _execute_step(step, *, run_id: int, product_id: int, model_name: str) -> dict[str, Any]:
    name = str(step["step_name"])
    base, _, suffix = name.partition(":")
    prospect_id = int(suffix) if suffix else None
    if base == "profile":
        return _run_profile_or_icp(step, product_id=product_id, model_name=model_name, workflow="profile")
    if base == "icp":
        return _run_profile_or_icp(step, product_id=product_id, model_name=model_name, workflow="icp")
    if base == "signals" and prospect_id is not None:
        return _run_signals(step, product_id=product_id, prospect_id=prospect_id, model_name=model_name)
    if base == "problem_statement" and prospect_id is not None:
        return _run_problem_statement(step, product_id=product_id, prospect_id=prospect_id, model_name=model_name)
    if base == "draft" and prospect_id is not None:
        return _run_draft(step, product_id=product_id, prospect_id=prospect_id, model_name=model_name)
    if base == "ranking":
        ranking = ranking_workflow.rank_product(product_id)
        scored = [item for item in ranking["prospects"] if item["score"] is not None]
        return {
            "prospect_count": ranking["prospect_count"],
            "scored_count": len(scored),
            "icp_status": ranking["icp_status"],
            "top_prospect_id": scored[0]["prospect_id"] if scored else None,
        }
    raise ValueError(f"unsupported pipeline step {name!r}")


def execute_pipeline_run(run_id: int, model_name: str) -> dict[str, Any]:
    """Resume a persisted pipeline, stopping only when local Ollama is unavailable."""
    conn = db.connect()
    try:
        run = db.get_pipeline_run(conn, run_id)
        if run is None:
            raise ValueError(f"pipeline run {run_id} not found")
        if run["status"] in {"done", "failed"}:
            return pipeline_run_payload(conn, run)
        product_id = int(run["product_id"])
        if db.get_product(conn, product_id) is None:
            db.update_pipeline_run(conn, run_id, status="failed")
            raise ValueError("pipeline product was deleted")
        model_name = str(model_name or run["model_name"] or llm_client.resolve_model_name(None))
        db.update_pipeline_run(conn, run_id, status="running", model_name=model_name)
        steps = db.list_pipeline_steps(conn, run_id)
    finally:
        conn.close()

    for step in steps:
        if step["status"] in _TERMINAL_STEP_STATUSES:
            continue
        step_id = int(step["id"])
        name = str(step["step_name"])
        skip_reason = _critical_step_failure_reason(run_id) or _skip_dependency(name, run_id)
        if skip_reason:
            conn = db.connect()
            try:
                db.update_pipeline_step(
                    conn, step_id, status="skipped", last_error=skip_reason
                )
            finally:
                conn.close()
            continue

        conn = db.connect()
        try:
            db.update_pipeline_step(conn, step_id, status="running", last_error=None)
        finally:
            conn.close()
        try:
            result = _execute_step(
                step, run_id=run_id, product_id=product_id, model_name=model_name
            )
        except llm_client.OllamaUnavailable as exc:
            conn = db.connect()
            try:
                db.update_pipeline_step(
                    conn,
                    step_id,
                    status="queued",
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                db.update_pipeline_run(
                    conn, run_id, status="queued", model_name=model_name
                )
            finally:
                conn.close()
            raise
        except Exception as exc:
            logger.exception("pipeline step failed run_id=%s step=%s", run_id, name)
            conn = db.connect()
            try:
                db.update_pipeline_step(
                    conn,
                    step_id,
                    status="failed",
                    last_error=f"{type(exc).__name__}: {exc}",
                )
            finally:
                conn.close()
            continue

        skipped = result.get("status") == "skipped"
        reason = result.get("reason") if skipped else None
        conn = db.connect()
        try:
            db.update_pipeline_step(
                conn,
                step_id,
                status="skipped" if skipped else "done",
                last_error=str(reason) if reason else None,
                result=result,
            )
        finally:
            conn.close()

    conn = db.connect()
    try:
        final_steps = db.list_pipeline_steps(conn, run_id)
        failed = any(step["status"] == "failed" for step in final_steps)
        final_status = "failed" if failed else "done"
        db.update_pipeline_run(conn, run_id, status=final_status, model_name=model_name)
        return pipeline_run_payload(conn, db.get_pipeline_run(conn, run_id))
    finally:
        conn.close()


def _handle_queued_pipeline(payload: dict[str, Any]) -> None:
    try:
        run_id = int(payload["pipeline_run_id"])
        product_id = int(payload["product_id"])
        model_name = str(payload.get("model_name") or "").strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("workflow.pipeline requires pipeline_run_id and product_id") from exc
    conn = db.connect()
    try:
        run = db.get_pipeline_run(conn, run_id)
        if run is None or int(run["product_id"]) != product_id:
            raise ValueError("queued pipeline task does not match its persisted run")
        if run["status"] in {"done", "failed"}:
            return
    finally:
        conn.close()
    execute_pipeline_run(run_id, model_name)


def register_pipeline_handler() -> None:
    """Register the full product pipeline as an Ollama-dependent queue task."""
    register_handler(TASK_TYPE, _handle_queued_pipeline, requires_ollama=True)
