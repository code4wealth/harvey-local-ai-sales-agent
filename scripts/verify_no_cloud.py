#!/usr/bin/env python3
"""Fail if cloud inference SDKs, endpoints, or keys appear in repository text."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANNED = [
    r"\bopenai\b",
    r"\banthropic\b",
    r"google[-_.]generativeai",
    r"\bgemini\b",
    r"\bcodex\b",
    r"api\.openai\.com",
    r"api\.anthropic\.com",
    r"generativelanguage\.googleapis\.com",
    r"\bgroq\b",
    r"together\.ai",
    r"api\.cohere",
    r"api\.mistral\.ai",
    r"openrouter",
    r"OPENAI_API_KEY",
    r"ANTHROPIC_API_KEY",
    r"GEMINI_API_KEY",
    r"\bclaude\b",
]
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".egg-info",
    ".claude",
    "test_evidence",
    "dist",
    "build",
}
EXCLUDE_FILES = {
    "CLAUDE.md",
    "AGENTS.md",
    "README_PACK.md",
    "START_PROMPT.md",
    "verify_no_cloud.py",
    "package-lock.json",
}
EXTS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
    ".example",
    ".cfg",
    ".ini",
    ".html",
    ".md",
}
DOCS_ALLOWED = {
    "COST_STATEMENT.md",
    "MODELS_AND_LICENCES.md",
    "PRD.md",
    "WORKFLOWS.md",
    "TASKS.md",
    "ACCEPTANCE_CHECKLIST.md",
    "ARCHITECTURE.md",
    "KNOWN_LIMITATIONS.md",
    "README.md",
}
# The sole additional path exception requested for the Phase 0 audit.
DOCS_DEV_ALLOWLIST = pathlib.PurePosixPath("docs/dev")
PATTERN = re.compile("|".join(BANNED), re.IGNORECASE)


def _is_allowed_development_note(relative_path: pathlib.PurePosixPath) -> bool:
    return relative_path == DOCS_DEV_ALLOWLIST or DOCS_DEV_ALLOWLIST in relative_path.parents


def _check_source_urls(path: pathlib.Path, relative: str) -> list[str]:
    if relative != "app/llm_client.py":
        return []
    allowed = {"http://127.0.0.1:11434"}
    contents = path.read_text(encoding="utf-8", errors="ignore")
    urls = re.findall(r"https?://[^\s\"']+", contents)
    issues = []
    for url in urls:
        clean = url.rstrip(".,);]}")
        if clean not in allowed:
            issues.append(f"{relative}: non-local URL {clean}")
    return issues


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative_path = pathlib.PurePosixPath(path.relative_to(ROOT).as_posix())
        if any(
            part in EXCLUDE_DIRS or part.endswith(".egg-info")
            for part in relative_path.parts
        ):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if _is_allowed_development_note(relative_path):
            continue
        if path.suffix.lower() not in EXTS and not path.name.startswith(".env"):
            continue
        if path.suffix.lower() == ".md" and path.name in DOCS_ALLOWED:
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            if PATTERN.search(line):
                hits.append(
                    f"{relative_path}:{line_number}: {line.strip()[:120]}"
                )
        hits.extend(_check_source_urls(path, relative_path.as_posix()))

    if hits:
        print("FAIL: inference-provider references found:\n" + "\n".join(hits))
        return 1
    print("PASS: no prohibited inference-provider references; Ollama client is local-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
