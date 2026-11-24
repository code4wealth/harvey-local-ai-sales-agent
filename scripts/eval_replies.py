#!/usr/bin/env python3
"""Evaluate local reply classifications without exposing text or labels to inference."""

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
from app.workflows import replies as reply_workflow  # noqa: E402
from scripts import import_replies  # noqa: E402

REPLY_LABELS_PATH = ROOT / "data" / "eval" / "reply_labels.csv"
REPLIES_PATH = ROOT / "data" / "sample" / "replies.csv"
FROZEN_PROMPT_PATH = ROOT / "data" / "eval" / "frozen_reply_prompt.sha256"
RUN_DIR = ROOT / "test_evidence" / "real_run"
DEFAULT_EVAL_DB = RUN_DIR / "replies-evaluation.db"
REPLY_LABEL_FIELDS = (
    "sample_label",
    "reply_id",
    "ground_truth_label",
    "difficulty",
    "split",
)
REPLY_LABEL_ORDER = (
    "interested",
    "meeting_request",
    "not_interested",
    "question",
    "out_of_office",
    "wrong_person",
    "unsubscribe",
    "other",
)
REPLY_LABELS = set(REPLY_LABEL_ORDER)
REPLY_DIFFICULTIES = {"clear", "ambiguous"}
REPLY_SPLITS = {"development", "held_out"}
EXPECTED_REPLY_IDS = {f"R{number:03d}" for number in range(1, 61)}
EXPECTED_SPLIT_COUNTS = {"development": 36, "held_out": 24}
EXPECTED_DIFFICULTY_COUNTS = {
    "development": {"clear": 26, "ambiguous": 10},
    "held_out": {"clear": 14, "ambiguous": 10},
}
UNRESOLVED_LABEL = "unresolved"
PREDICTED_LABEL_ORDER = (*REPLY_LABEL_ORDER, UNRESOLVED_LABEL)


class ReplyLabelValidationError(ValueError):
    """The reply-label ground truth does not match the frozen corpus contract."""


def load_reply_labels(
    expected_reply_ids: set[str] | None = None,
    *,
    path: Path | None = None,
    print_summary: bool = True,
) -> list[dict[str, str]]:
    """Load and validate reply labels without exposing or returning reply text."""
    label_path = path or REPLY_LABELS_PATH
    if not label_path.is_file():
        raise ReplyLabelValidationError("reply label file is missing")
    try:
        with label_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            rows = list(reader)
    except OSError as exc:
        raise ReplyLabelValidationError("reply label file could not be read") from exc

    if fields != list(REPLY_LABEL_FIELDS):
        raise ReplyLabelValidationError(
            "reply_labels.csv columns must be exactly " + ",".join(REPLY_LABEL_FIELDS)
        )
    if len(rows) != 60:
        raise ReplyLabelValidationError(f"reply_labels.csv must contain 60 rows, got {len(rows)}")

    reply_ids = [row.get("reply_id", "").strip() for row in rows]
    expected_ids = expected_reply_ids if expected_reply_ids is not None else EXPECTED_REPLY_IDS
    if len(set(reply_ids)) != len(reply_ids):
        raise ReplyLabelValidationError("reply_labels.csv contains duplicate reply IDs")
    if set(reply_ids) != expected_ids:
        raise ReplyLabelValidationError("reply-label IDs must match replies.csv exactly")
    if any(row.get("sample_label", "").strip() != "SAMPLE" for row in rows):
        raise ReplyLabelValidationError("reply_labels.csv rows must be marked SAMPLE")
    for row in rows:
        reply_id = row.get("reply_id", "").strip()
        if row.get("ground_truth_label", "").strip() not in REPLY_LABELS:
            raise ReplyLabelValidationError(f"unsupported or missing label for {reply_id}")
        if row.get("difficulty", "").strip() not in REPLY_DIFFICULTIES:
            raise ReplyLabelValidationError(f"unsupported or missing difficulty for {reply_id}")
        if row.get("split", "").strip() not in REPLY_SPLITS:
            raise ReplyLabelValidationError(f"unsupported or missing split for {reply_id}")

    split_counts = Counter(row["split"].strip() for row in rows)
    if dict(split_counts) != EXPECTED_SPLIT_COUNTS:
        raise ReplyLabelValidationError("reply-label splits must be development=36 and held_out=24")

    held_out_label_counts = Counter(
        row["ground_truth_label"].strip() for row in rows if row["split"].strip() == "held_out"
    )
    if set(held_out_label_counts) != REPLY_LABELS or min(held_out_label_counts.values()) < 3:
        raise ReplyLabelValidationError("every held-out reply label must have at least 3 examples")

    difficulty_counts = {
        split: Counter(
            row["difficulty"].strip() for row in rows if row["split"].strip() == split
        )
        for split in sorted(REPLY_SPLITS)
    }
    for split, expected in EXPECTED_DIFFICULTY_COUNTS.items():
        if dict(difficulty_counts[split]) != expected:
            raise ReplyLabelValidationError(f"unexpected difficulty counts for {split}")

    if print_summary:
        print("PASS: 60 reply labels; development=36, held_out=24")
        print("PASS: every held-out label has at least 3 examples")
        print(
            "Reply difficulty counts by split: "
            + "; ".join(
                f"{split}=clear:{difficulty_counts[split]['clear']},"
                f"ambiguous:{difficulty_counts[split]['ambiguous']}"
                for split in ("development", "held_out")
            )
        )
    return rows


def reply_prompt_hash() -> str:
    """Hash the full classification prompt with a fixed placeholder reply."""
    template = reply_workflow.build_reply_prompt("__REPLY_TEXT__")
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def _read_frozen_prompt() -> str:
    if not FROZEN_PROMPT_PATH.is_file():
        raise ValueError(
            "frozen reply-prompt hash is missing; run --freeze-prompt before held-out evaluation"
        )
    entries = FROZEN_PROMPT_PATH.read_text(encoding="utf-8").strip().split()
    if len(entries) != 1 or not re.fullmatch(r"[0-9a-f]{64}", entries[0]):
        raise ValueError("invalid frozen reply-prompt hash; use --refreeze to replace it")
    return entries[0]


def _check_frozen_prompt(current_hash: str) -> str:
    frozen_hash = _read_frozen_prompt()
    if current_hash != frozen_hash:
        raise ValueError(
            "reply prompt hash differs from the frozen held-out baseline "
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
                    "reply prompt hash differs from the existing frozen hash "
                    f"(current={current_hash}, frozen={frozen_hash}); use --refreeze to replace it"
                )
    FROZEN_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_PROMPT_PATH.write_text(current_hash + "\n", encoding="utf-8")
    return current_hash


def _parse_only(value: str | None) -> set[str] | None:
    if value is None:
        return None
    selected = {item.strip().upper() for item in value.split(",") if item.strip()}
    if not selected or any(re.fullmatch(r"R\d{3}", item) is None for item in selected):
        raise ValueError("--only must be a comma-separated list such as R003,R021")
    return selected


def _report_path(output_path: str | None, mode: str, model_name: str) -> Path:
    if output_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
        return RUN_DIR / f"replies-{mode}-{safe_model}-{stamp}.json"
    candidate = Path(output_path).expanduser()
    if not candidate.is_absolute():
        candidate = RUN_DIR / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(RUN_DIR.resolve()):
        raise ValueError("--output must be inside test_evidence/real_run/")
    return resolved


def _selected_rows(
    *, held_out: bool, only: str | None
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    split = "held_out" if held_out else "development"
    label_rows = [
        row for row in load_reply_labels(print_summary=False) if row["split"].strip() == split
    ]
    selected_ids = _parse_only(only)
    ids_in_split = {row["reply_id"].strip() for row in label_rows}
    if selected_ids is not None:
        missing = selected_ids - ids_in_split
        if missing:
            raise ValueError(
                f"--only IDs are not in the {split.replace('_', '-')} set: "
                + ",".join(sorted(missing))
            )
        label_rows = [row for row in label_rows if row["reply_id"].strip() in selected_ids]
    label_rows.sort(key=lambda row: row["reply_id"])
    if not label_rows:
        raise ValueError("no replies were selected for evaluation")

    text_rows = import_replies.load_reply_rows(REPLIES_PATH)
    text_by_id = {row["reply_id"]: row for row in text_rows}
    selected_ids = {row["reply_id"] for row in label_rows}
    if not selected_ids <= set(text_by_id):
        raise ValueError("selected reply labels do not have matching text-only reply rows")
    selected_text_rows = [text_by_id[row["reply_id"]] for row in label_rows]
    return label_rows, selected_text_rows


def _prepare_eval_database(db_path: str, text_rows: list[dict[str, str]]) -> None:
    conn = db.connect(db_path)
    try:
        db.init_db(conn)
        # Only text-only rows are imported. The labels never enter the application database.
        db.upsert_sample_replies(conn, text_rows)
    finally:
        conn.close()


def _classification_for(reply_id: str, model_name: str) -> dict[str, Any]:
    try:
        return reply_workflow.submit_reply_classification(reply_id, model=model_name)
    except llm_client.OllamaUnavailable:
        return reply_workflow.reply_classification_payload(reply_id)
    except reply_workflow.ReplyClassificationError:
        return reply_workflow.reply_classification_payload(reply_id)


def _build_report_metrics(
    label_rows: list[dict[str, str]], predictions: dict[str, str | None]
) -> dict[str, Any]:
    matrix = {
        actual: {predicted: 0 for predicted in PREDICTED_LABEL_ORDER}
        for actual in REPLY_LABEL_ORDER
    }
    difficulty_totals: dict[str, Counter[str]] = {
        difficulty: Counter(correct=0, total=0)
        for difficulty in ("clear", "ambiguous")
    }
    correct_total = 0
    misclassified_ids: list[str] = []
    for row in label_rows:
        reply_id = row["reply_id"]
        expected = row["ground_truth_label"]
        predicted = predictions.get(reply_id)
        prediction_bucket = predicted if predicted in REPLY_LABELS else UNRESOLVED_LABEL
        matrix[expected][prediction_bucket] += 1
        correct = predicted == expected
        correct_total += int(correct)
        difficulty_totals[row["difficulty"]]["total"] += 1
        difficulty_totals[row["difficulty"]]["correct"] += int(correct)
        if not correct:
            misclassified_ids.append(reply_id)

    per_label_accuracy: dict[str, dict[str, Any]] = {}
    for label in REPLY_LABEL_ORDER:
        total = sum(matrix[label].values())
        correct = matrix[label][label]
        per_label_accuracy[label] = {
            "correct": correct,
            "total": total,
            "accuracy": correct / total if total else None,
        }
    per_difficulty_accuracy = {
        difficulty: {
            "correct": values["correct"],
            "total": values["total"],
            "accuracy": values["correct"] / values["total"] if values["total"] else None,
        }
        for difficulty, values in difficulty_totals.items()
    }
    total = len(label_rows)
    return {
        "overall_accuracy": {
            "correct": correct_total,
            "total": total,
            "accuracy": correct_total / total if total else None,
        },
        "per_label_accuracy": per_label_accuracy,
        "per_difficulty_accuracy": per_difficulty_accuracy,
        "confusion_matrix": {
            "actual_labels": list(REPLY_LABEL_ORDER),
            "predicted_labels": list(PREDICTED_LABEL_ORDER),
            "counts": matrix,
        },
        "misclassified_ids": misclassified_ids,
        "unresolved_count": sum(prediction not in REPLY_LABELS for prediction in predictions.values()),
    }


def run_evaluation(
    *,
    model: str | None,
    db_path: str,
    held_out: bool = False,
    only: str | None = None,
    freeze_prompt: bool = False,
    refreeze: bool = False,
    output_path: str | None = None,
) -> int:
    current_prompt_hash = reply_prompt_hash()
    if freeze_prompt:
        if held_out:
            raise ValueError("--freeze-prompt is a standalone action and cannot be combined with --held-out")
        _freeze_prompt(current_prompt_hash, refreeze=refreeze)
        print(
            "Frozen reply-prompt hash written: "
            f"{current_prompt_hash} ({FROZEN_PROMPT_PATH})"
        )
        return 0
    if refreeze:
        raise ValueError("--refreeze requires --freeze-prompt")

    # Enforce the prompt freeze before loading any held-out labels or text.
    frozen_hash = _check_frozen_prompt(current_prompt_hash) if held_out else None
    label_rows, text_rows = _selected_rows(held_out=held_out, only=only)
    model_name = llm_client.resolve_model_name(model)
    db_path = str(Path(db_path).expanduser().resolve())
    os.environ["DB_PATH"] = db_path
    _prepare_eval_database(db_path, text_rows)

    predictions: dict[str, str | None] = {}
    for index, row in enumerate(label_rows, start=1):
        reply_id = row["reply_id"]
        result = _classification_for(reply_id, model_name)
        label = result.get("label") if result.get("status") == "succeeded" else None
        predictions[reply_id] = label if label in REPLY_LABELS else None
        print(f"Classified {index}/{len(label_rows)} replies (ID {reply_id})")

    metrics = _build_report_metrics(label_rows, predictions)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "held-out" if held_out else "development",
        "run_config": {
            "model": model_name,
            "think": False,
            "temperature": llm_client.DEFAULT_TEMPERATURE,
            "seed": llm_client.DEFAULT_SEED,
            "num_ctx": reply_workflow.NUM_CTX,
            "reply_prompt_sha256": current_prompt_hash,
            "frozen_reply_prompt_sha256": frozen_hash,
        },
        "selected_count": len(label_rows),
        **metrics,
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
    accuracy = metrics["overall_accuracy"]
    print(
        f"Reply classification accuracy: {accuracy['correct']}/{accuracy['total']} "
        f"({accuracy['accuracy']:.1%})"
    )
    print("Per-label accuracy: " + json.dumps(metrics["per_label_accuracy"], sort_keys=True))
    print("Per-difficulty accuracy: " + json.dumps(metrics["per_difficulty_accuracy"], sort_keys=True))
    print("Confusion matrix: " + json.dumps(metrics["confusion_matrix"], sort_keys=True))
    print("Misclassified reply IDs: " + ",".join(metrics["misclassified_ids"] or ["none"]))
    print(f"Redacted report saved: {destination}")
    return 0 if accuracy["correct"] == accuracy["total"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="local Ollama model name")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_EVAL_DB),
        help="isolated SQLite database for reply-evaluation runs",
    )
    parser.add_argument(
        "--freeze-prompt",
        action="store_true",
        help="standalone action: write the current reply-prompt SHA-256 and exit",
    )
    parser.add_argument(
        "--refreeze",
        action="store_true",
        help="allow --freeze-prompt to replace a different existing hash",
    )
    parser.add_argument(
        "--held-out",
        action="store_true",
        help="evaluate the 24 reserved replies; requires a matching frozen prompt hash",
    )
    parser.add_argument(
        "--only",
        default=None,
        metavar="R003,R021",
        help="evaluate only these reply IDs within the selected split",
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
            freeze_prompt=args.freeze_prompt,
            refreeze=args.refreeze,
            output_path=args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"reply evaluation could not start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
