"""Keep offline labels and evaluation paths out of runtime code."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
SCRIPTS_DIR = ROOT / "scripts"

GROUND_TRUTH_REFERENCE = re.compile(
    r"data[/\\](?:eval|evaluation)(?:[/\\]|\b)|"
    r"sample[_-]case[_-]notes|case[_ -]?notes|"
    r"\bexpected(?:[_-][a-z]+)*\.(?:csv|json)\b|signal[_-]holdout|"
    r"reply[_-]labels|sample[/\\]replies\.csv|sample_replies\s*\.\s*json|"
    r"ground[_ -]?truth|\bheld[_-]out\b|\bdifficulty\b|\bcase[_ -]type\b",
    re.IGNORECASE,
)
REPLY_ONLY_REFERENCE = re.compile(
    r"reply[_-]labels|sample[/\\]replies\.csv|sample_replies\s*\.\s*json|"
    r"\bdifficulty\b|\breply[_-]split\b",
    re.IGNORECASE,
)
ALLOWED_EVALUATOR_FILE = re.compile(r"eval_[^/]+\.py\Z")
REPLY_LABEL_PATH_REFERENCE = re.compile(r"reply[_-]labels\.csv", re.IGNORECASE)


def _text_sources(directory: Path):
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def test_runtime_app_does_not_reference_evaluation_or_ground_truth() -> None:
    violations = [
        f"{path.relative_to(APP_DIR)} references evaluation/ground-truth data"
        for path, source in _text_sources(APP_DIR)
        if GROUND_TRUTH_REFERENCE.search(source)
    ]
    assert not violations, (
        "Runtime app code must not know evaluation paths, labels, splits, or case annotations.\n"
        + "\n".join(violations)
    )


def test_only_offline_evaluators_and_validator_may_read_ground_truth() -> None:
    violations: list[str] = []
    for path, source in _text_sources(SCRIPTS_DIR):
        if not GROUND_TRUTH_REFERENCE.search(source):
            continue
        relative = path.relative_to(SCRIPTS_DIR).as_posix()
        if relative != "validate_corpus.py" and not ALLOWED_EVALUATOR_FILE.fullmatch(relative):
            violations.append(f"{relative} references ground-truth data")
    assert not violations, (
        "Only scripts/eval_*.py and scripts/validate_corpus.py may read ground truth.\n"
        + "\n".join(violations)
    )


def test_only_reply_evaluator_may_reference_reply_label_file() -> None:
    script_references = {
        path.relative_to(SCRIPTS_DIR).as_posix()
        for path, source in _text_sources(SCRIPTS_DIR)
        if REPLY_LABEL_PATH_REFERENCE.search(source)
    }
    app_references = [
        path.relative_to(APP_DIR).as_posix()
        for path, source in _text_sources(APP_DIR)
        if REPLY_LABEL_PATH_REFERENCE.search(source)
    ]
    assert script_references == {"eval_replies.py"}
    assert not app_references, "runtime app code must never reference reply-label ground truth"


def test_signal_evaluator_does_not_reference_reply_data_or_labels() -> None:
    path = SCRIPTS_DIR / "eval_signals.py"
    assert path.is_file(), "the offline signal evaluator must exist"
    source = path.read_text(encoding="utf-8")
    assert not REPLY_ONLY_REFERENCE.search(source), (
        "Signal evaluation must not read reply texts, reply labels, or reply annotations."
    )
