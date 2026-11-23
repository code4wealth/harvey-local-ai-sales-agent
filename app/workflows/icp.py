"""Generate a product-specific ideal-customer profile from its stored profile."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import db, llm_client
from app.queue_worker import register_handler
from app.workflows import common
from app.workflows.profile import BusinessProfile

TASK_TYPE = "workflow.icp"
MAX_DOCUMENT_CHARS = 3000
NUM_CTX = 4096


class CompanySize(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    min: int | None = Field(ge=0)
    max: int | None = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "CompanySize":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("company_size.min must not exceed company_size.max")
        return self


class IdealCustomerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    industries: list[str]
    company_size: CompanySize
    buyer_titles: list[str]
    pain_points: list[str]
    trigger_events: list[str]
    disqualifiers: list[str]


ICP_EXAMPLE = {
    "industries": ["independent bookstores"],
    "company_size": {"min": None, "max": None},
    "buyer_titles": ["shop owner"],
    "pain_points": ["seasonal inventory planning"],
    "trigger_events": ["opening a new storefront"],
    "disqualifiers": ["organizations without a retail shop"],
}


def build_icp_prompt(stored_profile: str) -> str:
    example = json.dumps(ICP_EXAMPLE, ensure_ascii=False, separators=(",", ":"))
    return (
        "Create an ideal-customer profile using only facts supported by the stored business profile. "
        "Do not invent industries, sizes, titles, pains, events, or exclusions. Use [\"not stated\"] "
        "for unsupported list fields. If the profile gives no numeric company-size basis, set both "
        "company_size.min and company_size.max to null. Return only JSON matching the schema.\n"
        f"Example JSON (fictional bookstore; format only): {example}\n"
        f"Stored business profile:\n{stored_profile[:MAX_DOCUMENT_CHARS]}"
    )


def _stored_profile(product_id: int) -> str:
    conn = db.connect()
    try:
        if db.get_product(conn, product_id) is None:
            raise common.ProductNotFound(f"product {product_id} not found")
        row = db.latest_business_profile(conn, product_id)
        if row is None:
            raise common.WorkflowInputError("no stored business profile exists for this product")
        raw_profile = str(row["profile_json"])
    finally:
        conn.close()

    try:
        parsed = json.loads(raw_profile)
        profile = BusinessProfile.model_validate(parsed)
    except (json.JSONDecodeError, ValueError) as exc:
        raise common.WorkflowInputError(f"stored business profile is invalid: {exc}") from exc
    return json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def execute_icp_run(product_id: int, run_id: int, model_name: str) -> IdealCustomerProfile:
    """Run one already-persisted ICP task using only this product's stored profile."""
    common.update_run(run_id, status="running", model_name=model_name)
    stored_profile = _stored_profile(product_id)
    generated = llm_client.generate_json(
        build_icp_prompt(stored_profile),
        IdealCustomerProfile,
        model=model_name,
        task=f"icp:{run_id}",
        retries=2,
        num_ctx=NUM_CTX,
    )
    if not isinstance(generated, IdealCustomerProfile):
        raise TypeError("ICP generator returned an unexpected schema type")
    common.complete_run(
        run_id=run_id,
        product_id=product_id,
        workflow="icp",
        result=generated.model_dump(mode="json"),
        model_name=model_name,
    )
    return generated


def submit_icp(product_id: int, *, model: str | None = None) -> int:
    """Run an ICP immediately, queueing the same task if Ollama is unavailable."""
    run_id = common.create_run(product_id, "icp", model)
    model_name = model
    try:
        model_name = llm_client.resolve_model_name(model)
        execute_icp_run(product_id, run_id, model_name)
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
                workflow="icp",
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


def _handle_queued_icp(payload: dict[str, Any]) -> None:
    try:
        product_id = int(payload["product_id"])
        run_id = int(payload["workflow_run_id"])
        model_name = str(payload["model_name"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("workflow.icp requires product_id, workflow_run_id, and model_name") from exc
    if not model_name:
        raise ValueError("workflow.icp task has no model_name")
    try:
        execute_icp_run(product_id, run_id, model_name)
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


def register_icp_handler() -> None:
    register_handler(TASK_TYPE, _handle_queued_icp)
