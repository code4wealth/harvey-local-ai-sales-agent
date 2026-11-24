#!/usr/bin/env python3
"""Run offline signal diagnostics against development or held-out SAMPLE pages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db, llm_client  # noqa: E402
from app.workflows import signals as signal_workflow  # noqa: E402

DATA_DIR = ROOT / "data"
EVAL_DIR = DATA_DIR / "eval"
EXPECTED_SIGNALS_PATH = EVAL_DIR / "expected_signals.csv"
HOLDOUT_EXPECTED_PATH = EVAL_DIR / "signal_holdout" / "expected.csv"
FROZEN_PROMPT_PATH = EVAL_DIR / "frozen_signal_prompt.sha256"
PRODUCT_CSVS = (
    DATA_DIR / "prospects" / "SAMPLE_relaycue.csv",
    DATA_DIR / "prospects" / "SAMPLE_fieldnest.csv",
)
RUN_DIR = ROOT / "test_evidence" / "real_run"
DEFAULT_EVAL_DB = RUN_DIR / "signals-evaluation.db"
EXPECTED_PROSPECTS = 37
EXPECTED_HOLDOUT = 12
NOISY_PROSPECTS = ("P033", "P034", "P035")
DROP_KEYS = ("quote", "type", "other_company", "negated", "stale")
SIGNAL_TYPES = {
    "funding",
    "hiring",
    "expansion",
    "leadership_change",
    "tech_change",
    "pain_mention",
}
TRAP_TYPES = {"no_signal", "implied", "negated", "stale", "other_company"}
TRAP_GROUPS: dict[str, set[str]] = {
    "no-signal/implied": {"no_signal", "implied"},
    "negated": {"negated"},
    "stale": {"stale"},
    "other-company": {"other_company"},
}


def _read_csv(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    if fields != expected_fields:
        raise ValueError(f"{path.relative_to(ROOT)} columns must be {expected_fields}, got {fields}")
    if not rows:
        raise ValueError(f"{path.relative_to(ROOT)} is empty")
    if any(row.get("sample_label", "").strip() != "SAMPLE" for row in rows):
        raise ValueError(f"{path.relative_to(ROOT)} contains an unlabelled row")
    return rows


def _pipe_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split("|") if item.strip())


def _annotation_from_row(row: dict[str, str]) -> dict[str, Any]:
    expected = _pipe_values(row.get("expected_types", ""))
    if expected == ("none",):
        expected = ()
    return {
        "case_type": row["case_type"],
        "expected_types": expected,
        "trap_types": _pipe_values(row.get("trap_types", "")),
        "scored": row.get("scored", "true").casefold() == "true",
    }


def _load_expected_annotations() -> dict[str, dict[str, Any]]:
    rows = _read_csv(
        EXPECTED_SIGNALS_PATH,
        ["sample_label", "prospect_id", "case_type", "expected_types", "trap_types", "scored"],
    )
    annotations = {row["prospect_id"].strip().upper(): _annotation_from_row(row) for row in rows}
    if len(annotations) != EXPECTED_PROSPECTS or len(rows) != EXPECTED_PROSPECTS:
        raise ValueError(f"expected {EXPECTED_PROSPECTS} unique prospect signal annotations")
    for row in rows:
        prospect_id = row["prospect_id"].strip().upper()
        if row["scored"].casefold() not in {"true", "false"}:
            raise ValueError(f"scored must be true/false for {prospect_id}")
    for prospect_id, annotation in annotations.items():
        expected = set(annotation["expected_types"])
        traps = set(annotation["trap_types"])
        if not expected <= SIGNAL_TYPES or not traps <= TRAP_TYPES:
            raise ValueError(f"unsupported expected signal or trap for {prospect_id}")
        if annotation["scored"] and not expected and not traps:
            raise ValueError(f"scored case has no expected outcome for {prospect_id}")
        if traps and expected:
            raise ValueError(f"trap case cannot expect positive signals for {prospect_id}")
        if not annotation["scored"] and (expected or traps):
            raise ValueError(f"unscored case cannot have signal truth for {prospect_id}")
    return annotations


def _load_unique_prospect_rows() -> dict[str, dict[str, str]]:
    rows_by_id: dict[str, dict[str, str]] = {}
    for csv_path in PRODUCT_CSVS:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                prospect_id = Path(row["page_text_path"]).stem.upper()
                previous = rows_by_id.get(prospect_id)
                if previous is not None and previous["page_text_path"] != row["page_text_path"]:
                    raise ValueError(f"duplicate prospect source differs for {prospect_id}")
                rows_by_id.setdefault(prospect_id, row)
    if len(rows_by_id) != EXPECTED_PROSPECTS:
        raise ValueError(f"expected {EXPECTED_PROSPECTS} unique prospect pages, got {len(rows_by_id)}")
    return dict(sorted(rows_by_id.items()))


def _load_held_out_cases() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    rows = _read_csv(
        HOLDOUT_EXPECTED_PATH,
        ["sample_label", "prospect_id", "page_path", "case_type", "expected_types", "trap_type"],
    )
    if len(rows) != EXPECTED_HOLDOUT:
        raise ValueError(f"expected {EXPECTED_HOLDOUT} held-out signal pages, got {len(rows)}")

    annotations: dict[str, dict[str, Any]] = {}
    page_rows: dict[str, dict[str, str]] = {}
    covered_signals: set[str] = set()
    covered_traps: set[str] = set()
    for row in rows:
        prospect_id = row["prospect_id"].strip().upper()
        relative_page = row["page_path"].replace("\\", "/")
        if Path(relative_page).stem.upper() != prospect_id:
            raise ValueError(f"held-out page path does not match {prospect_id}")
        page_path = (ROOT / relative_page).resolve()
        allowed_root = (DATA_DIR / "prospect_pages").resolve()
        if not page_path.is_relative_to(allowed_root) or not page_path.is_file():
            raise ValueError(f"held-out page is missing or outside prospect_pages: {relative_page}")
        page_text = page_path.read_text(encoding="utf-8")
        company_match = re.search(r"^Company:\s*(.+?)\s*$", page_text, re.MULTILINE)
        if company_match is None:
            raise ValueError(f"held-out page has no Company heading: {relative_page}")
        expected = _pipe_values(row["expected_types"])
        trap = row["trap_type"].strip()
        if trap:
            if trap not in TRAP_TYPES or expected != ("none",):
                raise ValueError(f"invalid held-out trap expectation for {prospect_id}")
            trap_types = (trap,)
            expected = ()
            covered_traps.add(trap)
        else:
            if not expected or "none" in expected or not set(expected) <= SIGNAL_TYPES:
                raise ValueError(f"held-out positive {prospect_id} must list supported signal types")
            trap_types = ()
            covered_signals.update(expected)
        annotations[prospect_id] = {
            "case_type": row["case_type"],
            "expected_types": expected,
            "trap_types": trap_types,
            "scored": True,
        }
        page_rows[prospect_id] = {
            "company_name": company_match.group(1),
            "company_domain": f"{prospect_id.casefold()}.example",
            "page_text_path": relative_page,
        }

    expected_ids = {f"P{number:03d}" for number in range(38, 50)}
    if set(annotations) != expected_ids:
        raise ValueError("held-out signal IDs must be exactly P038-P049")
    if covered_signals != SIGNAL_TYPES or covered_traps != TRAP_TYPES:
        raise ValueError("held-out signal pages must cover all signal types and required trap cases")
    return dict(sorted(annotations.items())), dict(sorted(page_rows.items()))


def _prepare_eval_prospects(db_path: str, rows_by_id: dict[str, dict[str, str]]) -> dict[str, int]:
    conn = db.connect(db_path)
    try:
        db.init_db(conn)
        product = conn.execute(
            "SELECT id FROM products WHERE name = ? ORDER BY id LIMIT 1",
            ("SAMPLE signal evaluation",),
        ).fetchone()
        product_id = (
            int(product["id"])
            if product is not None
            else db.create_product(conn, name="SAMPLE signal evaluation")
        )
        conn.commit()
        prospect_ids: dict[str, int] = {}
        for prospect_id, row in rows_by_id.items():
            page_path = row["page_text_path"]
            existing = conn.execute(
                "SELECT id FROM prospects WHERE product_id = ? AND page_text_path = ? "
                "ORDER BY id LIMIT 1",
                (product_id, page_path),
            ).fetchone()
            if existing is None:
                created = db.create_prospect(
                    conn,
                    product_id=product_id,
                    company_name=row["company_name"],
                    company_domain=row.get("company_domain", ""),
                    page_text_path=page_path,
                )
                conn.commit()
                prospect_ids[prospect_id] = created
            else:
                prospect_ids[prospect_id] = int(existing["id"])
        return prospect_ids
    finally:
        conn.close()


def _parse_only(value: str | None) -> set[str] | None:
    if value is None:
        return None
    selected = {item.strip().upper() for item in value.split(",") if item.strip()}
    if not selected or any(re.fullmatch(r"P\d{3}", item) is None for item in selected):
        raise ValueError("--only must be a comma-separated list such as P012,P028")
    return selected


def signal_prompt_hash() -> str:
    """Hash the prompt template, replacing its intentionally dynamic date."""
    template = signal_workflow.build_signal_prompt("__SIGNAL_PAGE_TEXT__")
    template = re.sub(
        r"today's UTC date, \d{4}-\d{2}-\d{2}",
        "today's UTC date, <UTC_DATE>",
        template,
        count=1,
    )
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def _read_frozen_prompt() -> str:
    if not FROZEN_PROMPT_PATH.is_file():
        raise ValueError(
            "frozen signal-prompt hash is missing; run --freeze-prompt before a held-out evaluation"
        )
    entries = FROZEN_PROMPT_PATH.read_text(encoding="utf-8").strip().split()
    if len(entries) != 1 or not re.fullmatch(r"[0-9a-f]{64}", entries[0]):
        raise ValueError("invalid frozen signal-prompt hash; use --refreeze to replace it")
    return entries[0]


def _check_frozen_prompt(current_hash: str) -> str:
    frozen_hash = _read_frozen_prompt()
    if current_hash != frozen_hash:
        raise ValueError(
            "signal prompt hash differs from the frozen held-out baseline "
            f"(current={current_hash}, frozen={frozen_hash})"
        )
    return frozen_hash


def _freeze_prompt(current_hash: str, *, refreeze: bool = False) -> str:
    if FROZEN_PROMPT_PATH.exists():
        try:
            frozen_hash = _read_frozen_prompt()
        except ValueError as exc:
            if not refreeze:
                raise ValueError(f"{exc}; use --refreeze to replace it") from exc
        else:
            if frozen_hash != current_hash and not refreeze:
                raise ValueError(
                    "signal prompt hash differs from the existing frozen hash "
                    f"(current={current_hash}, frozen={frozen_hash}); use --refreeze to replace it"
                )
    FROZEN_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_PROMPT_PATH.write_text(current_hash + "\n", encoding="utf-8")
    return current_hash


def _evaluate_one(annotation: dict[str, Any], payload: dict[str, Any] | None) -> bool:
    if payload is None or payload.get("status") != "succeeded":
        return False
    kept = payload.get("signals") or []
    kept_types = {item["type"] for item in kept}
    if not annotation["scored"]:
        return True
    expected = set(annotation["expected_types"])
    if expected:
        return expected <= kept_types
    if annotation["trap_types"]:
        return not kept_types
    return True


def _read_run(prospect_db_id: int) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = db.latest_signal_run(conn, prospect_db_id)
        return signal_workflow.signal_run_payload(row) if row is not None else None
    finally:
        conn.close()


def _read_inference_diagnostics(run_id: int | None) -> list[dict[str, Any]]:
    if run_id is None:
        return []
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT model, prompt_tokens, eval_tokens, seconds, load_seconds, "
            "temperature, seed, repeat_penalty, status, created_at "
            "FROM inference_log WHERE task = ? ORDER BY id",
            (f"signals:{int(run_id)}",),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _run_one(
    prospect_db_id: int,
    model: str | None,
    diagnostics: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    diagnostics.setdefault("raw_replies", [])
    try:
        signal_workflow.submit_signals(
            prospect_db_id,
            model=model,
            diagnostics=diagnostics,
            on_raw=diagnostics["raw_replies"].append,
        )
        return _read_run(prospect_db_id), None
    except llm_client.OllamaUnavailable as exc:
        run_id = getattr(exc, "signal_run_id", None)
        if run_id is None:
            return _read_run(prospect_db_id), f"{type(exc).__name__}: {exc}"
        conn = db.connect()
        try:
            row = db.get_signal_run(conn, int(run_id))
            payload = signal_workflow.signal_run_payload(row) if row is not None else None
        finally:
            conn.close()
        return payload, f"{type(exc).__name__}: {exc}"
    except signal_workflow.SignalRunError as exc:
        conn = db.connect()
        try:
            row = db.get_signal_run(conn, exc.run_id)
            payload = signal_workflow.signal_run_payload(row) if row is not None else None
        finally:
            conn.close()
        return payload, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return _read_run(prospect_db_id), f"{type(exc).__name__}: {exc}"


def _model_none_count(
    payload: dict[str, Any] | None, diagnostics: dict[str, Any] | None
) -> int:
    """Count only a successful run whose parsed model result had no signals."""
    if payload is None or payload.get("status") != "succeeded":
        return 0
    if diagnostics is None or "parsed_signals" not in diagnostics:
        return 0
    parsed = diagnostics["parsed_signals"]
    return int(isinstance(parsed, list) and not parsed)


def _trap_outcome(
    payload: dict[str, Any] | None, diagnostics: dict[str, Any] | None = None
) -> str:
    if payload is None or payload.get("status") != "succeeded":
        return "unresolved"
    drop_counts = payload.get("drop_counts") or {}
    if payload.get("signals") or any(
        int(drop_counts.get(key, 0) or 0) > 0
        for key in DROP_KEYS
    ):
        return "exercised"
    if _model_none_count(payload, diagnostics) > 0:
        return "empty-list"
    return "unclassified"


def _case_result(
    prospect_id: str,
    annotation: dict[str, Any],
    payload: dict[str, Any] | None,
    error: str | None,
    diagnostics: dict[str, Any],
    *,
    verbose: bool,
    held_out: bool,
    detailed: bool,
) -> tuple[bool, dict[str, Any]]:
    passed = _evaluate_one(annotation, payload)
    kept = payload.get("signals") or [] if payload is not None else []
    raw_drops = payload.get("drop_counts") or {} if payload is not None else {}
    drops = {key: int(raw_drops.get(key, 0) or 0) for key in DROP_KEYS}
    parsed = diagnostics.get("parsed_signals")
    parsed_count = len(parsed) if isinstance(parsed, list) else 0
    filtered_count = diagnostics.get("signals_returned_then_filtered")
    if filtered_count is None and isinstance(parsed, list):
        filtered_count = max(0, parsed_count - len(kept))
    filtered_count = int(filtered_count or 0)
    model_none = _model_none_count(payload, diagnostics)
    quote_retries = int(payload.get("quote_retries", 0) or 0) if payload else 0
    inference = _read_inference_diagnostics(int(payload["id"])) if payload else []
    removed_lines = diagnostics.get("removed_lines") or []
    raw_replies = diagnostics.get("raw_replies") or []

    if held_out:
        # Reserved reports are restricted to IDs and counts: no model text,
        # evidence, page content, annotation labels, or exception messages.
        result = {
            "passed_count": int(passed),
            "failed_count": int(not payload or payload.get("status") != "succeeded"),
            "kept_signal_count": len(kept),
            "parsed_signal_count": parsed_count,
            "parsed_output_count": int(isinstance(parsed, list)),
            "signals_returned_then_filtered": filtered_count,
            "quote_retries": quote_retries,
            "model_none_count": model_none,
            "drop_counts": drops,
            "removed_line_count": len(removed_lines),
            "cleaned_text_length": int(diagnostics.get("cleaned_text_length", 0) or 0),
            "truncated_count": int(bool(diagnostics.get("truncated", False))),
            "raw_reply_count": len(raw_replies),
            "inference_attempt_count": len(inference),
        }
        print(
            f"{prospect_id} passed_count={int(passed)} kept_signal_count={len(kept)} "
            f"quote_retries={quote_retries} model_none_count={model_none} "
            f"filtered_signal_count={filtered_count} "
            f"drop_counts={json.dumps(drops, sort_keys=True)} "
            f"failed_count={int(not payload or payload.get('status') != 'succeeded')}"
        )
        return passed, result

    result = {
        "case_type": annotation["case_type"],
        "expected_types": list(annotation["expected_types"]),
        "trap_types": list(annotation["trap_types"]),
        "scored": bool(annotation["scored"]),
        "status": payload.get("status") if payload else None,
        "signals": kept,
        "drop_counts": drops,
        "model_none_count": model_none,
        "signals_returned": parsed_count if isinstance(parsed, list) else None,
        "signals_returned_then_filtered": filtered_count,
        "quote_retries": quote_retries,
        "trap_outcome": _trap_outcome(payload, diagnostics) if annotation["trap_types"] else None,
        "error": error,
        "inference": inference,
        "diagnostics": {
            "removed_lines": removed_lines,
            "cleaned_text_length": int(diagnostics.get("cleaned_text_length", 0) or 0),
            "truncated": bool(diagnostics.get("truncated", False)),
            "truncated_characters": int(diagnostics.get("truncated_characters", 0) or 0),
            "raw_replies": raw_replies,
            "parsed_signals": parsed,
            "drop_details": diagnostics.get("drop_details", []),
        },
    }
    kept_types = [item["type"] for item in kept]
    expected = ",".join(annotation["expected_types"]) or ("none" if annotation["trap_types"] else "fit-only")
    print(
        f"{prospect_id} case_type={annotation['case_type']} expected={expected} "
        f"kept={','.join(kept_types) or 'none'} quote_retries={quote_retries} "
        f"model_none={model_none} "
        f"{'PASS' if passed else 'FAIL'}"
        + (f" error={error}" if error else "")
    )
    if verbose and detailed:
        print(f"  removed_lines={json.dumps(removed_lines, ensure_ascii=False)}")
        print(
            "  cleaned_text="
            + json.dumps(
                {
                    "length": result["diagnostics"]["cleaned_text_length"],
                    "truncated": result["diagnostics"]["truncated"],
                    "truncated_characters": result["diagnostics"]["truncated_characters"],
                },
                sort_keys=True,
            )
        )
        print(f"  raw_replies={json.dumps(raw_replies, ensure_ascii=False)}")
        print(f"  parsed_signals={json.dumps(parsed, ensure_ascii=False)}")
        print(f"  drops={json.dumps(result['diagnostics']['drop_details'], ensure_ascii=False)}")
    elif verbose:
        print(f"  diagnostics={json.dumps(result, ensure_ascii=False, sort_keys=True)}")
    return passed, result


def _report_path(output_path: str | None, mode: str, model_name: str) -> Path:
    if output_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
        return RUN_DIR / f"signals-{mode}-{safe_model}-{stamp}.json"
    candidate = Path(output_path).expanduser()
    if not candidate.is_absolute():
        candidate = RUN_DIR / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(RUN_DIR.resolve()):
        raise ValueError("--output must be inside test_evidence/real_run/")
    return resolved


def run_evaluation(
    *,
    model: str | None,
    db_path: str,
    held_out: bool = False,
    only: str | None = None,
    verbose: bool = False,
    freeze_prompt: bool = False,
    refreeze: bool = False,
    output_path: str | None = None,
) -> int:
    current_prompt_hash = signal_prompt_hash()
    if freeze_prompt:
        if held_out:
            raise ValueError("--freeze-prompt is a standalone action and cannot be combined with --held-out")
        _freeze_prompt(current_prompt_hash, refreeze=refreeze)
        print(
            "Frozen signal-prompt hash written: "
            f"{current_prompt_hash} ({FROZEN_PROMPT_PATH})"
        )
        return 0
    if refreeze:
        raise ValueError("--refreeze requires --freeze-prompt")

    frozen_hash = _check_frozen_prompt(current_prompt_hash) if held_out else None
    if held_out:
        annotations, rows_by_id = _load_held_out_cases()
    else:
        annotations = _load_expected_annotations()
        rows_by_id = _load_unique_prospect_rows()
        if set(annotations) != set(rows_by_id):
            raise ValueError("expected signal IDs do not match the 37 prospect pages")

    selected_ids = _parse_only(only)
    if selected_ids is not None:
        missing = selected_ids - set(rows_by_id)
        if missing:
            raise ValueError(
                f"--only IDs are not in the {'held-out' if held_out else 'development'} set: "
                + ",".join(sorted(missing))
            )
        annotations = {key: annotations[key] for key in sorted(selected_ids)}
        rows_by_id = {key: rows_by_id[key] for key in sorted(selected_ids)}

    model_name = llm_client.resolve_model_name(model)
    db_path = str(Path(db_path).expanduser().resolve())
    os.environ["DB_PATH"] = db_path
    prospect_db_ids = _prepare_eval_prospects(db_path, rows_by_id)
    results: dict[str, dict[str, Any] | None] = {}
    diagnostics_by_id: dict[str, dict[str, Any]] = {}
    details: dict[str, dict[str, Any]] = {}
    passes = 0

    print(
        f"Run config: mode={'held-out' if held_out else 'development'} model={model_name} "
        f"think=false temperature={llm_client.DEFAULT_TEMPERATURE:g} "
        f"seed={llm_client.DEFAULT_SEED} "
        f"repeat_penalty={llm_client.DEFAULT_REPEAT_PENALTY:g} "
        f"num_ctx={signal_workflow.NUM_CTX} "
        f"prompt_sha256={current_prompt_hash}"
        + (f" frozen_sha256={frozen_hash}" if frozen_hash else "")
    )
    for prospect_id in rows_by_id:
        diagnostics: dict[str, Any] = {}
        payload, error = _run_one(prospect_db_ids[prospect_id], model_name, diagnostics)
        results[prospect_id] = payload
        diagnostics_by_id[prospect_id] = diagnostics
        passed, case_details = _case_result(
            prospect_id,
            annotations[prospect_id],
            payload,
            error,
            diagnostics,
            verbose=verbose,
            held_out=held_out,
            detailed=verbose and selected_ids is not None and not held_out,
        )
        details[prospect_id] = case_details
        passes += int(passed)

    required = 0
    matched = 0
    for prospect_id, annotation in annotations.items():
        expected = annotation["expected_types"]
        if not expected:
            continue
        required += len(expected)
        payload = results[prospect_id]
        present = {
            item["type"] for item in (payload.get("signals") or [])
        } if payload is not None and payload.get("status") == "succeeded" else set()
        matched += sum(signal_type in present for signal_type in expected)
    print(
        f"Expected-signal recall: {matched}/{required} ({matched / required:.1%})"
        if required
        else "Expected-signal recall: n/a"
    )

    false_positives: Counter[str] = Counter()
    trap_totals: Counter[str] = Counter()
    trap_outcomes: dict[str, Counter[str]] = {group: Counter() for group in TRAP_GROUPS}
    for prospect_id, annotation in annotations.items():
        trap_types = set(annotation["trap_types"])
        if not trap_types:
            continue
        payload = results[prospect_id]
        outcome = _trap_outcome(payload, diagnostics_by_id[prospect_id])
        for group, matching_traps in TRAP_GROUPS.items():
            if not trap_types & matching_traps:
                continue
            trap_totals[group] += 1
            trap_outcomes[group][outcome] += 1
            if payload is not None and payload.get("status") == "succeeded" and payload.get("signals"):
                false_positives[group] += 1
    print(
        "Trap outcomes (exercised vs empty-list pass): "
        + "; ".join(
            f"{group}=exercised:{trap_outcomes[group]['exercised']}/"
            f"{trap_totals[group]}, empty-list:{trap_outcomes[group]['empty-list']}, "
            f"unresolved:{trap_outcomes[group]['unresolved']}, "
            f"persisted_false_positives:{false_positives[group]}"
            for group in TRAP_GROUPS
            if trap_totals[group]
        )
    )

    successful_runs = sum(
        1 for payload in results.values() if payload is not None and payload.get("status") == "succeeded"
    )
    model_none_counts = {
        prospect_id: _model_none_count(results[prospect_id], diagnostics_by_id[prospect_id])
        for prospect_id in results
    }
    model_none_runs = sum(model_none_counts.values())
    quote_retries_total = sum(
        int(payload.get("quote_retries", 0) or 0)
        for payload in results.values()
        if payload is not None
    )
    signals_returned = sum(
        int(diagnostics.get("signals_returned", 0) or 0)
        for diagnostics in diagnostics_by_id.values()
    )
    signals_filtered = sum(
        int(diagnostics.get("signals_returned_then_filtered", 0) or 0)
        for diagnostics in diagnostics_by_id.values()
    )
    aggregate_drops: Counter[str] = Counter({key: 0 for key in DROP_KEYS})
    for payload in results.values():
        for key, count in (payload.get("drop_counts") or {}).items() if payload else ():
            if key in DROP_KEYS:
                aggregate_drops[key] += int(count or 0)
    print(
        f"Model empty-list outputs: {model_none_runs}/{successful_runs} successful runs"
    )
    print(f"Signals returned then filtered: {signals_filtered} (returned={signals_returned})")
    print(f"Quote verification retries: {quote_retries_total}")
    print(
        "Aggregate verification drops: "
        + ", ".join(f"{key}={aggregate_drops[key]}" for key in DROP_KEYS)
    )

    noisy_ids = [prospect_id for prospect_id in NOISY_PROSPECTS if prospect_id in results]
    noisy_passes = 0
    for prospect_id in noisy_ids:
        payload = results[prospect_id]
        removed = payload.get("removed_content") if payload else None
        removed_lines = len(removed.get("lines", [])) if removed else 0
        no_kept_signals = (
            payload is not None
            and payload.get("status") == "succeeded"
            and not payload.get("signals")
        )
        passed = no_kept_signals and removed_lines > 0
        noisy_passes += int(passed)
        print(
            f"Noisy page {prospect_id}: removed_lines={removed_lines} "
            f"no_kept_signals={str(no_kept_signals).lower()} {'PASS' if passed else 'FAIL'}"
        )
    if not noisy_ids and not held_out:
        print("Noisy-page diagnostic: skipped (no noisy page selected)")

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "held-out" if held_out else "development",
        "run_config": {
            "model": model_name,
            "think": False,
            "temperature": llm_client.DEFAULT_TEMPERATURE,
            "seed": llm_client.DEFAULT_SEED,
            "repeat_penalty": llm_client.DEFAULT_REPEAT_PENALTY,
            "num_ctx": signal_workflow.NUM_CTX,
            "signal_prompt_sha256": current_prompt_hash,
            "frozen_signal_prompt_sha256": frozen_hash,
        },
        "selected_ids": list(rows_by_id),
        "counts": {
            "passed": passes,
            "total": len(rows_by_id),
            "successful_runs": successful_runs,
            "model_none_runs": model_none_runs,
            "quote_retries": quote_retries_total,
            "signals_returned": signals_returned,
            "signals_returned_then_filtered": signals_filtered,
            "aggregate_drop_counts": dict(aggregate_drops),
        },
        "trap_outcomes": {
            group: dict(trap_outcomes[group]) for group in TRAP_GROUPS if trap_totals[group]
        },
        "persisted_false_positives_on_traps": {
            group: false_positives[group] for group in TRAP_GROUPS if trap_totals[group]
        },
        "expected_signal_recall": {
            "matched": matched,
            "required": required,
            "rate": (matched / required) if required else None,
        },
        "noisy_page_diagnostic": {"selected_ids": noisy_ids, "passed_count": noisy_passes},
        "results": details,
    }
    destination = _report_path(
        output_path,
        "held-out" if held_out else "development",
        model_name,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Per-prospect evaluation: {passes}/{len(rows_by_id)} passed")
    print(f"Run diagnostics saved: {destination}")
    if not held_out:
        print("Fit-only annotations are not treated as signal truth; successful persistence is their pass criterion.")
    return 0 if passes == len(rows_by_id) and noisy_passes == len(noisy_ids) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="local Ollama model name")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_EVAL_DB),
        help="persistent isolated database for signal-evaluation runs",
    )
    parser.add_argument(
        "--freeze-prompt",
        action="store_true",
        help="standalone action: write the current prompt SHA-256 and exit without evaluation",
    )
    parser.add_argument(
        "--refreeze",
        action="store_true",
        help="allow --freeze-prompt to replace a different existing prompt hash",
    )
    parser.add_argument(
        "--held-out",
        action="store_true",
        help="evaluate only the 12 reserved signal holdout pages; always checks the frozen prompt hash",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print per-run diagnostics; with --only in development, include raw replies, parsed signals, removals, and drops",
    )
    parser.add_argument(
        "--only",
        default=None,
        metavar="P012,P028",
        help="evaluate only these prospect IDs within the selected set",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON report filename under test_evidence/real_run/ (defaults to a timestamped file)",
    )
    args = parser.parse_args(argv)
    try:
        return run_evaluation(
            model=args.model,
            db_path=args.db_path,
            held_out=args.held_out,
            only=args.only,
            verbose=args.verbose,
            freeze_prompt=args.freeze_prompt,
            refreeze=args.refreeze,
            output_path=args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"signal evaluation could not start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
