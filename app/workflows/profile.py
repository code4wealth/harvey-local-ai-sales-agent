"""Generate a validated business profile from one product's company-info file."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import db, llm_client
from app.queue_worker import register_handler
from app.workflows import common

TASK_TYPE = "workflow.profile"
MAX_DOCUMENT_CHARS = 3000
NUM_CTX = 4096
NOT_STATED = "not stated"
GENERAL_GROUNDING_THRESHOLD = 0.60
PAIN_POINT_GROUNDING_THRESHOLD = 0.80

_CONTENT_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOP_WORDS = frozenset(
    "a an and are as at be been being but by can could did do does for from had has have "
    "he her hers him his how i if in into is it its may might of on or our should that the "
    "their them then there these they this those through to under until up us was we were "
    "what when where which while who will with would you your".split()
)


class BusinessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    key_features: list[str] = Field(min_length=1)
    pain_points_solved: list[str] = Field(min_length=1)
    differentiators: list[str] = Field(min_length=1)
    typical_buyer: str = Field(min_length=1)
    typical_team_size: str = Field(min_length=1)
    working_situation: str = Field(min_length=1)
    not_for: list[str] = Field(min_length=1)


LEGACY_PROFILE_DEFAULTS: dict[str, Any] = {
    "typical_buyer": NOT_STATED,
    "typical_team_size": NOT_STATED,
    "working_situation": NOT_STATED,
    "not_for": [NOT_STATED],
}

PROFILE_EXAMPLE = {
    "summary": "A neighborhood food business prepares seasonal pastries for local markets.",
    "value_proposition": "Offers made-to-order cakes for community events.",
    "key_features": ["seasonal menu", "pre-order pickup"],
    "pain_points_solved": ["not stated"],
    "differentiators": ["not stated"],
    "typical_buyer": "not stated",
    "typical_team_size": "not stated",
    "working_situation": "not stated",
    "not_for": ["not stated"],
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


def _is_not_stated(value: str) -> bool:
    return value.strip().casefold() == NOT_STATED


def _word_coverage(claim: str, source_words: set[str]) -> float:
    claim_words = _content_words(claim)
    if not claim_words:
        return 1.0 if _is_not_stated(claim) else 0.0
    return len(claim_words & source_words) / len(claim_words)


def validate_profile_grounding(
    profile: BusinessProfile, document: str, product_name: str
) -> None:
    """Reject unsupported claims and summaries containing the stored product name
    or a near-variant.
    """
    if not isinstance(profile, BusinessProfile):
        raise TypeError("profile grounding requires a BusinessProfile")
    if not isinstance(product_name, str) or not product_name:
        raise TypeError("profile grounding requires the stored product name")
    source_words = _content_words(document)
    issues: list[str] = []
    validation_details: list[dict[str, Any]] = []
    for field_path, field_value in common.iter_string_fields(
        profile.model_dump(mode="python")
    ):
        for matched_text in common.ungrounded_stray_token_matches(field_value, document):
            check = (
                f"contains repeated-token artifact {matched_text!r} not found in source document"
            )
            issues.append(f"{field_path} {check}")
            validation_details.append(
                {"field": field_path, "check": check, "value": matched_text}
            )
    exact_name_matches = list(
        re.finditer(re.escape(product_name), profile.summary, flags=re.IGNORECASE)
    )
    for match in exact_name_matches:
        check = "must not contain the product name; display name comes from the products table"
        issues.append(f"summary {check}")
        validation_details.append(
            {"field": "summary", "check": check, "value": match.group(0)}
        )

    name_prefixes = [
        product_name[:length]
        for length in range(len(product_name) - 1, 3, -1)
    ]
    if name_prefixes:
        prefix_pattern = re.compile(
            "(?:" + "|".join(re.escape(prefix) for prefix in name_prefixes) + "):",
            flags=re.IGNORECASE,
        )
        for match in prefix_pattern.finditer(profile.summary):
            check = (
                "must not contain a case-insensitive prefix of at least four characters "
                "of the product name followed by a colon"
            )
            issues.append(f"summary {check}")
            validation_details.append(
                {"field": "summary", "check": check, "value": match.group(0)}
            )
    fields = (
        "summary",
        "value_proposition",
        "typical_buyer",
        "typical_team_size",
        "working_situation",
        "key_features",
        "pain_points_solved",
        "differentiators",
        "not_for",
    )
    for field_name in fields:
        value = getattr(profile, field_name)
        statements = value if isinstance(value, list) else [value]
        threshold = (
            PAIN_POINT_GROUNDING_THRESHOLD
            if field_name == "pain_points_solved"
            else GENERAL_GROUNDING_THRESHOLD
        )
        for index, statement in enumerate(statements):
            if _is_not_stated(statement):
                continue
            coverage = _word_coverage(statement, source_words)
            if coverage < threshold:
                location = f"{field_name}[{index}]" if isinstance(value, list) else field_name
                issues.append(
                    f"{location} has {coverage:.0%} content-word overlap; "
                    f"requires at least {threshold:.0%}"
                )
                validation_details.append(
                    {
                        "field": location,
                        "check": f"has {coverage:.0%} content-word overlap; requires at least {threshold:.0%}",
                        "value": statement,
                    }
                )
    if issues:
        raise llm_client.ValidationFailure(
            "profile grounding failed: " + "; ".join(issues),
            details=validation_details,
        )


def validate_stored_profile(value: Any) -> BusinessProfile:
    """Load both the current profile schema and previously stored profiles."""
    if not isinstance(value, dict):
        raise ValueError("stored business profile must be a JSON object")
    compatible = dict(value)
    for field_name, default in LEGACY_PROFILE_DEFAULTS.items():
        compatible.setdefault(field_name, default)
    for field_name in ("key_features", "pain_points_solved", "differentiators", "not_for"):
        if field_name in compatible and compatible[field_name] == []:
            compatible[field_name] = [NOT_STATED]
    return BusinessProfile.model_validate(compatible)


def build_profile_prompt(document: str, product_name: str) -> str:
    example = json.dumps(PROFILE_EXAMPLE, ensure_ascii=False, separators=(",", ":"))
    return (
        "Create a business profile using only facts stated in the company-info document. "
        "Do not infer or add outside facts. Return every field in the schema. For unsupported "
        "text fields, write \"not stated\"; for unsupported list fields, write [\"not stated\"]. "
        f"For the summary, describe what the product is and does without using the product name "
        f"{product_name!r}, for example, 'This workspace...' or 'A browser-based tool...'. "
        "The summary must not contain the product name or a case-insensitive prefix of at least "
        "four characters of that name followed by a colon. The display name always comes from "
        "the products table, never from model output. "
        "Include pain_points_solved only when the source states a problem or need. For each "
        "pain-point item, at least 80 percent of its distinct content words must also occur in "
        "the source text. Do not convert features or general benefits into an unstated pain. "
        "Return only JSON matching the schema.\n"
        f"Example JSON (fictional food business; format only): {example}\n"
        f"Company-info document:\n{document[:MAX_DOCUMENT_CHARS]}"
    )


def _profile_inputs(product_id: int) -> tuple[str, str]:
    conn = db.connect()
    try:
        product = db.get_product(conn, product_id)
        if product is None:
            raise common.ProductNotFound(f"product {product_id} not found")
        product_name = str(product["name"])
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
    return product_name, document[:MAX_DOCUMENT_CHARS]


def execute_profile_run(product_id: int, run_id: int, model_name: str) -> BusinessProfile:
    """Run one already-persisted profile task; exceptions remain visible to callers."""
    common.update_run(run_id, status="running", model_name=model_name)
    product_name, document = _profile_inputs(product_id)
    generated = llm_client.generate_json(
        build_profile_prompt(document, product_name),
        BusinessProfile,
        model=model_name,
        task=f"profile:{run_id}",
        retries=2,
        num_ctx=NUM_CTX,
        post_validate=lambda result: validate_profile_grounding(
            result, document, product_name
        ),
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
    run_id = common.create_run(
        product_id,
        "profile",
        model,
        temperature=llm_client.DEFAULT_TEMPERATURE,
        seed=llm_client.DEFAULT_SEED,
        repeat_penalty=llm_client.DEFAULT_REPEAT_PENALTY,
    )
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
