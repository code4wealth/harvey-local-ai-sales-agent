#!/usr/bin/env python3
"""Offline reply evaluation and its isolated ground-truth access helpers."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPLY_LABELS_PATH = ROOT / "data" / "eval" / "reply_labels.csv"
REPLY_LABEL_FIELDS = (
    "sample_label",
    "reply_id",
    "ground_truth_label",
    "difficulty",
    "split",
)
REPLY_LABELS = {
    "interested",
    "meeting_request",
    "not_interested",
    "question",
    "out_of_office",
    "wrong_person",
    "unsubscribe",
    "other",
}
REPLY_DIFFICULTIES = {"clear", "ambiguous"}
REPLY_SPLITS = {"development", "held_out"}
EXPECTED_REPLY_IDS = {f"R{number:03d}" for number in range(1, 61)}
EXPECTED_SPLIT_COUNTS = {"development": 36, "held_out": 24}
EXPECTED_DIFFICULTY_COUNTS = {
    "development": {"clear": 26, "ambiguous": 10},
    "held_out": {"clear": 14, "ambiguous": 10},
}


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
