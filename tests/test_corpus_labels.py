from __future__ import annotations

import csv

import pytest

from scripts import validate_corpus


def test_reply_data_stays_text_only_and_keeps_all_ids():
    ids = validate_corpus.validate_replies()
    assert ids == {f"R{number:03d}" for number in range(1, 61)}


def test_missing_operator_reply_labels_are_reported_and_pass(capsys, monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "sample").mkdir(parents=True)
    monkeypatch.setattr(validate_corpus, "DATA_DIR", data_dir)

    validate_corpus.validate_optional_reply_labels(
        {f"R{number:03d}" for number in range(1, 61)}
    )

    assert "reply_labels.csv not present yet" in capsys.readouterr().out


def test_present_but_empty_reply_labels_fail_validation(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    sample_dir = data_dir / "sample"
    sample_dir.mkdir(parents=True)
    with (sample_dir / "reply_labels.csv").open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(["reply_id", "label"])
    monkeypatch.setattr(validate_corpus, "DATA_DIR", data_dir)

    with pytest.raises(validate_corpus.CorpusValidationError, match="60 rows"):
        validate_corpus.validate_optional_reply_labels(
            {f"R{number:03d}" for number in range(1, 61)}
        )
