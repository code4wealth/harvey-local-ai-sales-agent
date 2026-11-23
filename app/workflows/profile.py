"""Generate a validated business profile from one product's company-info file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import db, llm_client
from app.queue_worker import register_handler
from app.workflows import common

TASK_TYPE = "workflow.profile"
MAX_DOCUMENT_CHARS = 3000
NUM_CTX = 4096


class BusinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    key_features: list[str]
    pain_points_solved: list[str]
    differentiators: list[str]


PROFILE_EXAMPLE = {
    "summary": "A bakery prepares seasonal pastries for neighborhood markets.",
    "value_proposition": "Offers made-to-order cakes for community events.",
    "key_features": ["seasonal menu", "pre-order pickup"],
    "pain_points_solved": ["not stated"],
    "differentiators": ["not stated"],
}


def build_profile_prompt(document: str) -> str:
    example = json.dumps(PROFILE_EXAMPLE, ensure_ascii=False, separators=(",", ":"))
    return (
        "Create a business profile using only facts stated in the company-info document. "
        "Do not infer or add outside facts. For unsupported text or list fields, write "
        '"not stated" (for a list, use ["not stated"]). Return only JSON matching the schema.\n'
        f"Example JSON (fictional bakery; format only): {example}\n"
        f"Company-info document:\n{document[:MAX_DOCUMENT_CHARS]}"
    )


def _company_info_document(product_id: int) -> str:
    conn = db.connect()
    try:
        product = db.get_product(conn, product_id)
        if product is None:
            raise common.ProductNotFound(f"product {product_id} not found")
        docs_path = str(product["docs_path"] or "").strip()
    finally:
        conn.close()

    if not docs_path:
        raise common.WorkflowInputError("product has no company-info file path")
    source = Path(docs_path)
    if not source.is_file():
        raise common.WorkflowInputError(f"company-info file does not exist: {docs_path}")
    try:
        document = source.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise common.WorkflowInputError(f"company-info file could not be read: {exc}") from exc
    if not document:
        raise common.WorkflowInputError("company-info file is empty")
    return document[:MAX_DOCUMENT_CHARS]


def execute_profile_run(product_id: int, run_id: int, model_name: str) -> BusinessProfile:
    """Run one already-persisted profile task; exceptions remain visible to callers."""
    common.update_run(run_id, status="running", model_name=model_name)
    document = _company_info_document(product_id)
    generated = llm_client.generate_json(
        build_profile_prompt(document),
        BusinessProfile,
        model=model_name,
        task=f"profile:{run_id}",
        retries=2,
        num_ctx=NUM_CTX,
    )
    if not isinstance(generated, BusinessProfile):
        # Defensive schema boundary: do not persist an unvalidated object.
        raise TypeError("profile generator returned an unexpected schema type")
    common.complete_run(
        run_id=run_id,
        product_id=product_id,
        workflow="profile",
        result=generated.model_dump(mode="json"),
        model_name=model_name,
    )
    return generated


def submit_profile(product_id: int, *, model: str | None = None) -> int:
    """Run a profile immediately, queueing the same task if Ollama is unavailable."""
    run_id = common.create_run(product_id, "profile", model)
    model_name = model
    try:
        model_name = llm_client.resolve_model_name(model)
        execute_profile_run(product_id, run_id, model_name)
        return run_id
    except llm_client.OllamaUnavailable as exc:
        if not model_name:
            error = f"{type(exc).__name__}: {exc}; no model name was resolved for replay"
            common.set_run_failure(run_id, error, model_name)
            raise common.WorkflowRunError(run_id, error) from exc
        try:
            task_id = common.queue_run(
                run_id=run_id,
                product_id=product_id,
                workflow="profile",
                task_type=TASK_TYPE,
                model_name=model_name,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception as queue_error:
            error = f"{type(exc).__name__}: {exc}; queueing failed: {queue_error}"
            common.set_run_failure(run_id, error, model_name)
            raise common.WorkflowRunError(run_id, error) from queue_error
        exc.workflow_run_id = run_id
        exc.queue_task_id = task_id
        raise
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        common.set_run_failure(run_id, error, model_name)
        raise common.WorkflowRunError(run_id, error) from exc


def _handle_queued_profile(payload: dict[str, Any]) -> None:
    try:
        product_id = int(payload["product_id"])
        run_id = int(payload["workflow_run_id"])
        model_name = str(payload["model_name"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("workflow.profile requires product_id, workflow_run_id, and model_name") from exc
    if not model_name:
        raise ValueError("workflow.profile task has no model_name")
    try:
        execute_profile_run(product_id, run_id, model_name)
    except llm_client.OllamaUnavailable as exc:
        common.update_run(
            run_id,
            status="queued",
            error=f"{type(exc).__name__}: {exc}",
            model_name=model_name,
        )
        raise
    except Exception as exc:
        common.set_run_failure(run_id, f"{type(exc).__name__}: {exc}", model_name)
        raise


def register_profile_handler() -> None:
    register_handler(TASK_TYPE, _handle_queued_profile)
