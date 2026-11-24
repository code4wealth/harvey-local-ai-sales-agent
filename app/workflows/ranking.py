"""Deterministic product-scoped prospect ranking; no LLM calls."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app import batch, db, prospects, scoring

HIGH_TIER_MIN = 70.0
MEDIUM_TIER_MIN = 40.0
ICP_FIELDS = ("industries", "pain_points", "trigger_events", "disqualifiers")
_KNOWN_ICP_KEYS = {
    "industries",
    "company_size",
    "company_size_min",
    "company_size_max",
    "buyer_titles",
    "pain_points",
    "trigger_events",
    "disqualifiers",
}


class ProductNotFound(LookupError):
    """The requested product does not exist."""


def _load_icp(conn, product_id: int) -> tuple[Any | None, dict[str, Any], str]:
    row = conn.execute(
        "SELECT id, icp_json, created_at FROM icps "
        "WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (int(product_id),),
    ).fetchone()
    if row is None:
        return None, {}, "missing"
    try:
        value = json.loads(row["icp_json"])
    except (TypeError, json.JSONDecodeError):
        return row, {}, "invalid"
    if not isinstance(value, dict) or not (_KNOWN_ICP_KEYS & value.keys()):
        return row, {}, "invalid"
    return row, value, "available"


def _signal_snapshot(conn, prospect_id: int, product_id: int) -> dict[str, Any]:
    latest = conn.execute(
        "SELECT id, status FROM signal_runs WHERE prospect_id = ? AND product_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (int(prospect_id), int(product_id)),
    ).fetchone()
    successful = conn.execute(
        "SELECT id, created_at FROM signal_runs "
        "WHERE prospect_id = ? AND product_id = ? AND status = 'succeeded' "
        "ORDER BY id DESC LIMIT 1",
        (int(prospect_id), int(product_id)),
    ).fetchone()
    if successful is None:
        return {
            "status": "missing",
            "latest_run_status": latest["status"] if latest is not None else None,
            "run_id": None,
            "created_at": None,
            "signals": None,
        }

    rows = conn.execute(
        "SELECT type, evidence, confidence FROM signals "
        "WHERE prospect_id = ? AND signal_run_id = ? ORDER BY id",
        (int(prospect_id), int(successful["id"])),
    ).fetchall()
    verified: list[dict[str, Any]] = []
    for row in rows:
        signal_type = str(row["type"] or "").strip().lower()
        evidence = str(row["evidence"] or "")
        try:
            confidence = float(row["confidence"])
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            signal_type in scoring.SIGNAL_WEIGHTS
            and evidence.strip()
            and 0.0 <= confidence <= 1.0
        ):
            verified.append(
                {"type": signal_type, "evidence": evidence, "confidence": confidence}
            )
    return {
        "status": "available" if verified else "none_found",
        "latest_run_status": latest["status"] if latest is not None else None,
        "run_id": int(successful["id"]),
        "created_at": successful["created_at"],
        "signals": verified,
    }


def _read_page(
    conn, prospect_id: int, *, page_dir: str | Path | None
) -> tuple[str, str]:
    try:
        page_text = prospects.load_prospect_page(conn, prospect_id, page_dir=page_dir)
    except FileNotFoundError:
        return "missing", ""
    except prospects.ProspectPageError:
        return "invalid", ""
    return ("available" if page_text.strip() else "empty"), page_text


def _not_stated(value: str) -> bool:
    return value.strip().casefold() == "not stated"


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip() and not _not_stated(item)]


def _literal_phrase_present(source: str, phrase: str) -> bool:
    normalized_source = scoring.normalize_evidence_text(source)
    normalized_phrase = scoring.normalize_evidence_text(phrase)
    if not normalized_source or not normalized_phrase:
        return False
    pattern = re.compile(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)")
    return pattern.search(normalized_source) is not None


def _text_field_match(field_name: str, icp: dict[str, Any], page_status: str, page_text: str) -> dict[str, Any]:
    values = _list_values(icp.get(field_name))
    method = "normalized exact phrase in stored local page text"
    if not values:
        return {
            "status": "unknown",
            "matches": [],
            "method": method,
            "reason": "The stored ICP has no stated values for this field.",
        }
    if page_status != "available":
        return {
            "status": "unknown",
            "matches": [],
            "method": method,
            "reason": "Local prospect page text is missing, invalid, or empty.",
        }
    matches = [value for value in values if _literal_phrase_present(page_text, value)]
    if field_name == "disqualifiers":
        status = "evidence_found" if matches else "no_exact_match"
        reason = (
            "An exact disqualifier phrase appears in the page text."
            if matches
            else "No exact disqualifier phrase appears; this does not establish semantic fit."
        )
    else:
        status = "matched" if matches else "no_exact_match"
        reason = (
            "At least one exact ICP phrase appears in the page text."
            if matches
            else "No exact ICP phrase appears; this does not establish semantic fit."
        )
    return {"status": status, "matches": matches, "method": method, "reason": reason}


def _company_size_match(prospect, icp: dict[str, Any]) -> dict[str, Any]:
    company_size = icp.get("company_size")
    if isinstance(company_size, dict):
        minimum, maximum = company_size.get("min"), company_size.get("max")
    else:
        minimum = icp.get("company_size_min")
        maximum = icp.get("company_size_max")
    employee_count = prospect["employee_count"]
    result = {
        "employee_count": employee_count,
        "range": {"min": minimum, "max": maximum},
        "method": "recorded employee count compared with the stored ICP bounds",
    }
    if employee_count is None or (minimum is None and maximum is None):
        return {**result, "status": "unknown", "reason": "Employee count or ICP size bounds are missing."}
    if isinstance(employee_count, bool):
        return {**result, "status": "unknown", "reason": "Employee count is invalid."}
    try:
        count = float(employee_count)
        lower = float(minimum) if minimum is not None else None
        upper = float(maximum) if maximum is not None else None
    except (TypeError, ValueError, OverflowError):
        return {**result, "status": "unknown", "reason": "Employee count or ICP size bounds are invalid."}
    if lower is not None and upper is not None and lower > upper:
        return {**result, "status": "unknown", "reason": "Stored ICP size bounds are invalid."}
    matched = (lower is None or count >= lower) and (upper is None or count <= upper)
    return {
        **result,
        "status": "matched" if matched else "not_matched",
        "reason": "Employee count falls within the stored range." if matched else "Employee count falls outside the stored range.",
    }


def _buyer_title_match(prospect, icp: dict[str, Any]) -> dict[str, Any]:
    contact_title = str(prospect["contact_title"] or "").strip()
    buyer_titles = _list_values(icp.get("buyer_titles"))
    method = "existing deterministic title keyword-fit heuristic"
    if not contact_title or not buyer_titles:
        return {
            "status": "unknown",
            "contact_title": contact_title or None,
            "matched_titles": [],
            "fit_score": None,
            "method": method,
            "reason": "Contact title or ICP buyer titles are missing.",
        }
    matched_titles = [
        title
        for title in buyer_titles
        if (fit := scoring.title_fit(contact_title, [title])) is not None and fit >= 60.0
    ]
    fit_score = scoring.title_fit(contact_title, buyer_titles)
    return {
        "status": "matched" if matched_titles else "no_keyword_match",
        "contact_title": contact_title,
        "matched_titles": matched_titles,
        "fit_score": fit_score,
        "method": method,
        "reason": (
            "The title heuristic found buyer-title keyword overlap."
            if matched_titles
            else "The title heuristic found no substantive buyer-title overlap."
        ),
    }


def _icp_field_matches(
    prospect, icp: dict[str, Any], page_status: str, page_text: str
) -> dict[str, Any]:
    return {
        "industries": _text_field_match("industries", icp, page_status, page_text),
        "company_size": _company_size_match(prospect, icp),
        "buyer_titles": _buyer_title_match(prospect, icp),
        "pain_points": _text_field_match("pain_points", icp, page_status, page_text),
        "trigger_events": _text_field_match("trigger_events", icp, page_status, page_text),
        "disqualifiers": _text_field_match("disqualifiers", icp, page_status, page_text),
    }


def _empty_icp_field_matches() -> dict[str, Any]:
    return {
        field_name: {
            "status": "unknown",
            "matches": [],
            "method": "unavailable",
            "reason": "No usable product ICP is stored.",
        }
        for field_name in ICP_FIELDS
    } | {
        "company_size": {
            "status": "unknown",
            "method": "unavailable",
            "reason": "No usable product ICP is stored.",
        },
        "buyer_titles": {
            "status": "unknown",
            "matched_titles": [],
            "fit_score": None,
            "method": "unavailable",
            "reason": "No usable product ICP is stored.",
        },
    }


def _tier(score_result: dict[str, Any] | None) -> str:
    if score_result is None:
        return "unranked"
    if score_result["partial"]:
        return "partial"
    score_value = float(score_result["score"])
    if score_value >= HIGH_TIER_MIN:
        return "high"
    if score_value >= MEDIUM_TIER_MIN:
        return "medium"
    return "low"


def rank_product(
    product_id: int, *, page_dir: str | Path | None = None
) -> dict[str, Any]:
    """Compute product-specific scores from stored ICP, verified signals, and local pages."""
    conn = db.connect()
    try:
        product = db.get_product(conn, product_id)
        if product is None:
            raise ProductNotFound(f"product {product_id} not found")
        icp_row, icp_data, icp_status = _load_icp(conn, product_id)
        ranked: list[dict[str, Any]] = []
        for prospect in db.list_prospects(conn, product_id):
            prospect_id = int(prospect["id"])
            signal_state = _signal_snapshot(conn, prospect_id, product_id)
            page_status, page_text = _read_page(
                conn, prospect_id, page_dir=page_dir
            )
            missing_inputs: list[str] = []
            if icp_status != "available":
                missing_inputs.append("icp")
            if signal_state["status"] == "missing":
                missing_inputs.append("signals")
            if page_status != "available":
                missing_inputs.append("page_text")

            score_result = None
            if icp_status == "available":
                score_result = batch.embed_and_score_prospect(
                    conn,
                    prospect_id,
                    page_dir=page_dir,
                    verified_signals=signal_state["signals"],
                )
            missing_components = (
                list(score_result["breakdown"]["missing_components"])
                if score_result is not None
                else []
            )
            evidence_reasons = [
                {
                    "type": signal["type"],
                    "evidence": signal["evidence"],
                    "confidence": signal["confidence"],
                    "signal_run_id": signal_state["run_id"],
                }
                for signal in (signal_state["signals"] or [])
            ]
            result = {
                "prospect_id": prospect_id,
                "product_id": int(product_id),
                "company_name": prospect["company_name"],
                "company_domain": prospect["company_domain"],
                "contact_title": prospect["contact_title"],
                "employee_count": prospect["employee_count"],
                "rank": None,
                "score": score_result["score"] if score_result is not None else None,
                "tier": _tier(score_result),
                "partial": score_result["partial"] if score_result is not None else True,
                "score_breakdown": score_result["breakdown"] if score_result is not None else None,
                "missing_inputs": missing_inputs,
                "missing_components": missing_components,
                "page_text_status": page_status,
                "signals_status": signal_state["status"],
                "latest_signal_run_status": signal_state["latest_run_status"],
                "signal_run_id": signal_state["run_id"],
                "verified_signal_reasons": evidence_reasons,
                "icp_field_matches": (
                    _icp_field_matches(prospect, icp_data, page_status, page_text)
                    if icp_status == "available"
                    else _empty_icp_field_matches()
                ),
            }
            ranked.append(result)

        ranked.sort(
            key=lambda item: (
                item["score"] is None,
                bool(item["partial"]),
                -(float(item["score"]) if item["score"] is not None else 0.0),
                item["prospect_id"],
            )
        )
        rank_number = 0
        for item in ranked:
            if item["score"] is not None:
                rank_number += 1
                item["rank"] = rank_number

        return {
            "product_id": int(product["id"]),
            "product_name": product["name"],
            "icp_status": icp_status,
            "icp_id": int(icp_row["id"]) if icp_row is not None else None,
            "icp_created_at": icp_row["created_at"] if icp_row is not None else None,
            "tier_thresholds": {
                "high_min": HIGH_TIER_MIN,
                "medium_min": MEDIUM_TIER_MIN,
                "low_max_exclusive": MEDIUM_TIER_MIN,
                "partial": "Any score with one or more missing components",
                "unranked": "No usable product ICP; score is null",
            },
            "prospect_count": len(ranked),
            "prospects": ranked,
        }
    finally:
        conn.close()
