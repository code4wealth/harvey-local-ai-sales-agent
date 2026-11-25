"""Helpers for hashing rendered prompts and identifying the checked-out source."""

from __future__ import annotations

import hashlib
import re
import subprocess
from functools import lru_cache
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_COMMIT_HASH = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")


def prompt_sha256(prompt: str) -> str:
    """Return the SHA-256 of the exact rendered UTF-8 prompt text."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def source_commit_hash() -> str:
    """Read the checked-out Git commit; report ``unknown`` in packaged builds."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = result.stdout.strip()
    return value if _COMMIT_HASH.fullmatch(value) else "unknown"


def prompt_traceability(prompt: str) -> dict[str, str]:
    return {"prompt_hash": prompt_sha256(prompt), "commit_hash": source_commit_hash()}
