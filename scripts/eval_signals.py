#!/usr/bin/env python3
"""Run signal extraction against all unique sample prospect pages."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db, llm_client  # noqa: E402
from app.workflows import signals as signal_workflow  # noqa: E402

DATA_DIR = ROOT / "data"
CASE_NOTES_PATH = DATA_DIR / "sample_case_notes.csv"
PRODUCT_CSVS = (
    DATA_DIR / "prospects" / "SAMPLE_relaycue.csv",
    DATA_DIR / "prospects" / "SAMPLE_fieldnest.csv",
)
DEFAULT_EVAL_DB = DATA_DIR / "signals-evaluation.db"
EXPECTED_PROSPECTS = 37
NOISY_PROSPECTS = ("P033", "P034", "P035")

EXPECTED_SIGNAL_TYPES: dict[str, tuple[str, ...]] = {
    "explicit_funding": ("funding",),
    "explicit_hiring": ("hiring",),
    "explicit_expansion": ("expansion",),
    "explicit_tech_change": ("tech_change",),
    "leadership_change": ("leadership_change",),
    "pain_mention": ("pain_mention",),
    "mixed_multi_signal": ("leadership_change", "expansion"),
}
TRAP_GROUPS = {
    "no-signal/implied": lambda value: value.startswith("no_signal")
    or value == "implied_not_stated",
    "negated": lambda value: value == "negated_signal",
    "stale": lambda value: value == "stale_signal",
    "third-party": lambda value: value == "third_party_signal",
}


def _load_case_annotations() -> dict[str, dict[str, str]]:
    with CASE_NOTES_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    if fields != ["sample_label", "prospect_id", "case_type", "annotation"]:
        raise ValueError("signal annotation file has unexpected columns")
    if any(row.get("sample_label") != "SAMPLE" for row in rows):
        raise ValueError("signal annotation file contains an unlabelled row")
    annotations = {row["prospect_id"].upper(): row for row in rows}
    if len(rows) != EXPECTED_PROSPECTS or len(annotations) != EXPECTED_PROSPECTS:
        raise ValueError(f"expected {EXPECTED_PROSPECTS} unique prospect annotations")
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


def _expected_types(case_type: str) -> tuple[str, ...] | None:
    return EXPECTED_SIGNAL_TYPES.get(case_type)


def _trap_group(case_type: str) -> str | None:
    for name, predicate in TRAP_GROUPS.items():
        if predicate(case_type):
            return name
    return None


def _evaluate_one(case_type: str, payload: dict[str, Any] | None) -> bool:
    if payload is None or payload["status"] != "succeeded":
        return False
    kept = payload["signals"] or []
    kept_types = {item["type"] for item in kept}
    expected = _expected_types(case_type)
    if expected is not None:
        return set(expected) <= kept_types
    if _trap_group(case_type) is not None:
        return not kept_types
    # Fit-only annotations do not assert signal ground truth; a successful
    # persisted extraction is the only pass criterion for those rows.
    return True


def _read_run(prospect_db_id: int) -> dict[str, Any] | None:
    conn = db.connect()
    try:
        row = db.latest_signal_run(conn, prospect_db_id)
        return signal_workflow.signal_run_payload(row) if row is not None else None
    finally:
        conn.close()


def _run_one(prospect_db_id: int, model: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        signal_workflow.submit_signals(prospect_db_id, model=model)
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


def _print_signal_result(
    prospect_id: str, case_type: str, payload: dict[str, Any] | None, error: str | None
) -> bool:
    passed = _evaluate_one(case_type, payload)
    kept = payload["signals"] if payload is not None else None
    drops = payload["drop_counts"] if payload is not None else None
    print(
        f"{prospect_id} case_type={case_type} "
        f"kept={json.dumps(kept, ensure_ascii=False, sort_keys=True)} "
        f"drop_counts={json.dumps(drops, ensure_ascii=False, sort_keys=True)} "
        f"{'PASS' if passed else 'FAIL'}"
        + (f" error={error}" if error else "")
    )
    return passed


def run_evaluation(*, model: str | None, db_path: str) -> int:
    annotations = _load_case_annotations()
    rows_by_id = _load_unique_prospect_rows()
    if set(annotations) != set(rows_by_id):
        raise ValueError("signal annotation IDs do not match the 37 prospect pages")

    db_path = str(Path(db_path).expanduser().resolve())
    os.environ["DB_PATH"] = db_path
    prospect_db_ids = _prepare_eval_prospects(db_path, rows_by_id)
    results: dict[str, dict[str, Any] | None] = {}
    passes = 0

    for prospect_id in rows_by_id:
        payload, error = _run_one(prospect_db_ids[prospect_id], model)
        results[prospect_id] = payload
        case_type = annotations[prospect_id]["case_type"]
        passes += int(_print_signal_result(prospect_id, case_type, payload, error))

    required = 0
    matched = 0
    for prospect_id, annotation in annotations.items():
        expected = _expected_types(annotation["case_type"])
        if expected is None:
            continue
        required += len(expected)
        payload = results[prospect_id]
        present = {
            item["type"] for item in (payload["signals"] or [])
        } if payload is not None and payload["status"] == "succeeded" else set()
        matched += sum(signal_type in present for signal_type in expected)
    print(
        f"Explicit-signal recall: {matched}/{required} "
        f"({matched / required:.1%})" if required else "Explicit-signal recall: n/a"
    )

    false_positives: Counter[str] = Counter()
    trap_totals: Counter[str] = Counter()
    for prospect_id, annotation in annotations.items():
        group = _trap_group(annotation["case_type"])
        if group is None:
            continue
        trap_totals[group] += 1
        payload = results[prospect_id]
        if payload is not None and payload["status"] == "succeeded" and payload["signals"]:
            false_positives[group] += 1
    print(
        "False positives on traps: "
        + "; ".join(
            f"{group}={false_positives[group]}/{trap_totals[group]}"
            for group in TRAP_GROUPS
        )
    )

    noisy_passes = 0
    for prospect_id in NOISY_PROSPECTS:
        payload = results[prospect_id]
        removed = payload["removed_content"] if payload is not None else None
        removed_lines = len(removed["lines"]) if removed is not None else 0
        no_kept_signals = (
            payload is not None
            and payload["status"] == "succeeded"
            and not payload["signals"]
        )
        passed = no_kept_signals and removed_lines > 0
        noisy_passes += int(passed)
        print(
            f"Noisy page {prospect_id}: removed_lines={removed_lines} "
            f"no_kept_signals={str(no_kept_signals).lower()} {'PASS' if passed else 'FAIL'}"
        )

    print(f"Per-prospect evaluation: {passes}/{EXPECTED_PROSPECTS} passed")
    print("Fit-only annotations are not treated as signal truth; their pass status means the run persisted.")
    return 0 if passes == EXPECTED_PROSPECTS and noisy_passes == len(NOISY_PROSPECTS) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="local Ollama model name")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_EVAL_DB),
        help="persistent isolated database for signal-evaluation runs",
    )
    args = parser.parse_args(argv)
    try:
        return run_evaluation(model=args.model, db_path=args.db_path)
    except (OSError, ValueError) as exc:
        print(f"signal evaluation could not start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
