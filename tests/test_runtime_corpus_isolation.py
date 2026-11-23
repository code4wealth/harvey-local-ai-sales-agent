"""Keep offline sample ground truth out of runtime application code."""

from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN_REFERENCES = {
    "case-note ground truth": re.compile(r"sample_case_notes\s*\.\s*csv", re.IGNORECASE),
    "reply ground-truth corpus": re.compile(r"sample_replies\s*\.\s*json", re.IGNORECASE),
    "held-out split": re.compile(r"\bheld[_-]out\b", re.IGNORECASE),
}


def test_runtime_app_does_not_reference_case_notes_or_held_out_ground_truth() -> None:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for description, pattern in FORBIDDEN_REFERENCES.items():
            if pattern.search(source):
                violations.append(f"{path.relative_to(APP_DIR)} references {description}")

    assert not violations, (
        "Runtime app code must not access sample case notes, the reply ground-truth corpus, "
        "or the held_out split; only an offline evaluation script may read held-out labels.\n"
        + "\n".join(violations)
    )
