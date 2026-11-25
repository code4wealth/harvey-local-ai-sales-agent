from __future__ import annotations

import csv
from collections import Counter

import pytest

from scripts import eval_replies, validate_corpus


def test_reply_data_stays_text_only_and_keeps_all_ids():
    ids = validate_corpus.validate_replies()
    assert ids == {f"R{number:03d}" for number in range(1, 61)}


def test_restored_reply_labels_have_exact_columns_and_requested_coverage(capsys):
    rows = eval_replies.load_reply_labels()
    assert tuple(rows[0].keys()) == eval_replies.REPLY_LABEL_FIELDS
    assert len(rows) == 60
    splits = Counter(row["split"] for row in rows)
    assert splits == {"development": 36, "held_out": 24}
    held_out_labels = Counter(
        row["ground_truth_label"] for row in rows if row["split"] == "held_out"
    )
    assert set(held_out_labels) == eval_replies.REPLY_LABELS
    assert min(held_out_labels.values()) >= 3
    output = capsys.readouterr().out
    assert "development=clear:26,ambiguous:10" in output
    assert "held_out=clear:14,ambiguous:10" in output


def test_corpus_validator_requires_restored_labels(monkeypatch, tmp_path):
    labels_path = tmp_path / "reply_labels.csv"
    monkeypatch.setattr(eval_replies, "REPLY_LABELS_PATH", labels_path)
    with pytest.raises(validate_corpus.CorpusValidationError, match="missing"):
        validate_corpus.validate_reply_labels(
            {f"R{number:03d}" for number in range(1, 61)}
        )


def test_present_but_empty_reply_labels_fail_validation(monkeypatch, tmp_path):
    labels_path = tmp_path / "reply_labels.csv"
    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(eval_replies.REPLY_LABEL_FIELDS)
    monkeypatch.setattr(eval_replies, "REPLY_LABELS_PATH", labels_path)

    with pytest.raises(validate_corpus.CorpusValidationError, match="60 rows"):
        validate_corpus.validate_reply_labels(
            {f"R{number:03d}" for number in range(1, 61)}
        )
