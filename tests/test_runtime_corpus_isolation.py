"""Keep offline labels out of runtime code and unrelated scripts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
SCRIPTS_DIR = ROOT / "scripts"
ALLOWED_CASE_NOTE_SCRIPTS = {"eval_signals.py", "eval_replies.py"}
CASE_NOTE_REFERENCE = re.compile(
    r"sample[_\s-]*case[_\s-]*notes|case[_\s-]*notes", re.IGNORECASE
)
FORBIDDEN_APP_REFERENCES = {
    "case-note ground truth": CASE_NOTE_REFERENCE,
    "reply ground-truth corpus": re.compile(r"sample_replies\s*\.\s*json", re.IGNORECASE),
    "held-out split": re.compile(r"\bheld[_-]out\b", re.IGNORECASE),
}
SIGNAL_EVAL_FORBIDDEN = re.compile(
    r"sample_replies\s*\.\s*json|\bheld[_-]out\b", re.IGNORECASE
)


def _text_sources(directory: Path):
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def test_runtime_app_does_not_reference_offline_ground_truth() -> None:
    violations: list[str] = []
    for path, source in _text_sources(APP_DIR):
        for description, pattern in FORBIDDEN_APP_REFERENCES.items():
            if pattern.search(source):
                violations.append(f"{path.relative_to(APP_DIR)} references {description}")

    assert not violations, (
        "Runtime app code must not access offline case labels, reply truth, or the held-out split.\n"
        + "\n".join(violations)
    )


def test_only_signal_and_reply_evaluators_may_reference_case_notes() -> None:
    violations: list[str] = []
    for path, source in _text_sources(SCRIPTS_DIR):
        if not CASE_NOTE_REFERENCE.search(source):
            continue
        if path.relative_to(SCRIPTS_DIR).as_posix() not in ALLOWED_CASE_NOTE_SCRIPTS:
            violations.append(f"{path.relative_to(SCRIPTS_DIR)} references case-note data")

    assert not violations, "Only the offline signal and reply evaluators may read case notes.\n" + "\n".join(
        violations
    )


def test_signal_evaluator_does_not_reference_reply_or_split_data() -> None:
    path = SCRIPTS_DIR / "eval_signals.py"
    assert path.is_file(), "the offline signal evaluator must exist"
    source = path.read_text(encoding="utf-8")
    assert not SIGNAL_EVAL_FORBIDDEN.search(source), (
        "Signal evaluation must not read the reply corpus or split labels."
    )
