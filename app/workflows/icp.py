"""Generate a product-specific ideal-customer profile from its stored profile."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import db, llm_client
from app.queue_worker import register_handler
from app.workflows import common
from app.workflows.profile import BusinessProfile, NOT_STATED, validate_stored_profile

TASK_TYPE = "workflow.icp"
MAX_DOCUMENT_CHARS = 3000
NUM_CTX = 4096
ICP_GROUNDING_THRESHOLD = 0.80
PRODUCT_RESTATEMENT_THRESHOLD = 0.60

_CONTENT_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOP_WORDS = frozenset(
    "a an and are as at be been being but by can could did do does for from had has have "
    "he her hers him his how i if in into is it its may might of on or our should that the "
    "their them then there these they this those through to under until up us was we were "
    "what when where which while who will with would you your".split()
)
_TRIGGER_EVENT = re.compile(
    r"\b(?:add(?:s|ed|ing)?|acquir(?:e|es|ed|ing)|adopt(?:s|ed|ing)?|appoint(?:s|ed|ing)?|"
    r"award(?:s|ed|ing)?|build(?:s|ing)?|clos(?:e|es|ed|ing)|contract(?:s|ed|ing)?|"
    r"deploy(?:s|ed|ing)?|expand(?:s|ed|ing)?|fund(?:s|ed|ing)?|grow(?:s|ing)?|"
    r"hir(?:e|es|ed|ing)|implement(?:s|ed|ing)?|launch(?:es|ed|ing)?|"
    r"merg(?:e|es|ed|ing)|mov(?:e|es|ed|ing)|open(?:s|ed|ing)?|"
    r"rais(?:e|es|ed|ing)|relocat(?:e|es|ed|ing)|replac(?:e|es|ed|ing)|"
    r"secur(?:e|es|ed|ing)|start(?:s|ed|ing)|switch(?:es|ed|ing)|"
    r"enter(?:s|ed|ing)|introduc(?:e|es|ed|ing)|install(?:s|ed|ing)|"
    r"establish(?:es|ed|ing)|commission(?:s|ed|ing)|relocat(?:e|es|ed|ing))\b",
    re.IGNORECASE,
)


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


def _canonical_word(word: str) -> str:
    word = word.casefold()
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        stem = word[:-3]
        return stem[:-1] if len(stem) > 2 and stem[-1] == stem[-2] else stem
    if len(word) > 4 and word.endswith("ed"):
        stem = word[:-2]
        if stem.endswith("dd"):
            return stem
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] in "mnprt":
            return stem[:-1]
        return stem + "e" if stem.endswith("g") else stem
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _content_words(text: str) -> set[str]:
    words = {_canonical_word(word) for word in _CONTENT_WORD.findall(text)}
    return {word for word in words if len(word) > 2 and word not in _STOP_WORDS}


def _word_coverage(claim: str, support_words: set[str]) -> float:
    claim_words = _content_words(claim)
    if not claim_words:
        return 0.0
    return len(claim_words & support_words) / len(claim_words)


def _is_not_stated(value: str) -> bool:
    return value.strip().casefold() == NOT_STATED


def _profile_items(profile: BusinessProfile, *fields: str) -> list[str]:
    values: list[str] = []
    for field_name in fields:
        value = getattr(profile, field_name)
        if isinstance(value, list):
            values.extend(item for item in value if not _is_not_stated(item))
        elif not _is_not_stated(value):
            values.append(value)
    return values


def _check_list_field(
    *,
    field_name: str,
    items: list[str],
    support: list[str],
    issues: list[str],
) -> None:
    support_words = _content_words(" ".join(support))
    for index, item in enumerate(items):
        if _is_not_stated(item):
            continue
        if not item.strip():
            issues.append(f"{field_name}[{index}] is empty; use an empty list or 'not stated'")
            continue
        coverage = _word_coverage(item, support_words)
        if coverage < ICP_GROUNDING_THRESHOLD:
            issues.append(
                f"{field_name}[{index}] has {coverage:.0%} profile-word overlap; "
                f"requires at least {ICP_GROUNDING_THRESHOLD:.0%}"
            )


def validate_icp_grounding(
    icp: IdealCustomerProfile, profile: BusinessProfile
) -> None:
    """Require every ICP claim to be grounded in the matching profile fields."""
    if not isinstance(icp, IdealCustomerProfile):
        raise TypeError("ICP grounding requires an IdealCustomerProfile")
    if not isinstance(profile, BusinessProfile):
        raise TypeError("ICP grounding requires a BusinessProfile source")

    issues: list[str] = []
    _check_list_field(
        field_name="industries",
        items=icp.industries,
        support=_profile_items(
            profile, "summary", "value_proposition", "typical_team_size", "working_situation"
        ),
        issues=issues,
    )
    _check_list_field(
        field_name="buyer_titles",
        items=icp.buyer_titles,
        support=_profile_items(profile, "typical_buyer"),
        issues=issues,
    )
    _check_list_field(
        field_name="pain_points",
        items=icp.pain_points,
        support=_profile_items(profile, "pain_points_solved", "working_situation"),
        issues=issues,
    )
    trigger_support = _profile_items(
        profile, "summary", "typical_team_size", "working_situation"
    )
    _check_list_field(
        field_name="trigger_events",
        items=icp.trigger_events,
        support=trigger_support,
        issues=issues,
    )
    disqualifier_support = _profile_items(profile, "not_for")
    _check_list_field(
        field_name="disqualifiers",
        items=icp.disqualifiers,
        support=disqualifier_support,
        issues=issues,
    )

    numeric_basis = {int(value) for value in re.findall(r"\b\d+\b", profile.typical_team_size)}
    for bound_name, bound_value in (
        ("min", icp.company_size.min),
        ("max", icp.company_size.max),
    ):
        if bound_value is not None and bound_value not in numeric_basis:
            issues.append(
                f"company_size.{bound_name}={bound_value} is not stated in typical_team_size"
            )

    product_words = _content_words(
        " ".join(_profile_items(profile, "summary", "value_proposition", "key_features"))
    )
    for field_name, items in (
        ("trigger_events", icp.trigger_events),
        ("disqualifiers", icp.disqualifiers),
    ):
        for index, item in enumerate(items):
            if _is_not_stated(item):
                continue
            if _word_coverage(item, product_words) >= PRODUCT_RESTATEMENT_THRESHOLD:
                issues.append(
                    f"{field_name}[{index}] restates the product or its features instead of a buyer condition"
                )
            if field_name == "trigger_events":
                event_match = _TRIGGER_EVENT.search(item)
                if event_match is None:
                    issues.append(
                        f"trigger_events[{index}] must describe a concrete external organizational event"
                    )
                else:
                    action = _canonical_word(event_match.group(0))
                    support_words = _content_words(" ".join(trigger_support))
                    if action not in support_words and f"{action}e" not in support_words:
                        issues.append(
                            f"trigger_events[{index}] uses an event action not stated in the profile"
                        )

    if issues:
        raise ValueError("ICP grounding failed: " + "; ".join(issues))


def build_icp_prompt(stored_profile: str) -> str:
    example = json.dumps(ICP_EXAMPLE, ensure_ascii=False, separators=(",", ":"))
    return (
        "Create an ideal-customer profile using only facts supported by the stored business profile. "
        "Use typical_buyer for buyer_titles, typical_team_size for company_size, "
        "pain_points_solved and working_situation for pain_points, and not_for for disqualifiers. "
        "Every non-empty item must be grounded in those profile fields. Do not invent industries, "
        "sizes, titles, pains, events, or exclusions. If a list field is unsupported, use [] or "
        "[\"not stated\"]. Set both company_size bounds to null unless numeric size is stated in "
        "typical_team_size. A trigger event must be a concrete external organizational change "
        "explicitly supported by the profile; do not restate the product, a feature, or the normal "
        "working situation as an event. Disqualifiers must come from not_for; do not restate the "
        "product or exclude organizations merely because they do not use it. Return only JSON "
        "matching the schema.\n"
        f"Example JSON (fictional bookstore; format only): {example}\n"
        f"Stored business profile:\n{stored_profile[:MAX_DOCUMENT_CHARS]}"
    )


def _stored_profile(product_id: int) -> BusinessProfile:
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
        return validate_stored_profile(parsed)
    except (json.JSONDecodeError, ValueError) as exc:
        raise common.WorkflowInputError(f"stored business profile is invalid: {exc}") from exc


def execute_icp_run(product_id: int, run_id: int, model_name: str) -> IdealCustomerProfile:
    """Run one already-persisted ICP task using only this product's stored profile."""
    common.update_run(run_id, status="running", model_name=model_name)
    stored_profile = _stored_profile(product_id)
    profile_data = stored_profile.model_dump(mode="json")
    ordered_profile = {
        field_name: profile_data[field_name]
        for field_name in (
            "typical_buyer",
            "typical_team_size",
            "working_situation",
            "pain_points_solved",
            "not_for",
            "summary",
            "value_proposition",
            "key_features",
            "differentiators",
        )
    }
    serialized_profile = json.dumps(ordered_profile, ensure_ascii=False, separators=(",", ":"))
    generated = llm_client.generate_json(
        build_icp_prompt(serialized_profile),
        IdealCustomerProfile,
        model=model_name,
        task=f"icp:{run_id}",
        retries=2,
        num_ctx=NUM_CTX,
        post_validate=lambda result: validate_icp_grounding(result, stored_profile),
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
    run_id = common.create_run(
        product_id,
        "icp",
        model,
        temperature=llm_client.DEFAULT_TEMPERATURE,
        seed=llm_client.DEFAULT_SEED,
    )
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
