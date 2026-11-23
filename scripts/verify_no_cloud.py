#!/usr/bin/env python3
"""Fail if cloud-AI SDKs, domains, or keys appear in the repo. Run before every commit."""
import re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
BANNED = [
    r"\bopenai\b", r"\banthropic\b", r"google[-_.]generativeai", r"\bgemini\b", r"\bcodex\b",
    r"api\.openai\.com", r"api\.anthropic\.com", r"generativelanguage\.googleapis\.com",
    r"\bgroq\b", r"together\.ai", r"api\.cohere", r"api\.mistral\.ai", r"openrouter",
    r"OPENAI_API_KEY", r"ANTHROPIC_API_KEY", r"GEMINI_API_KEY", r"\bclaude\b",
]
EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".claude", "test_evidence", "dist", "build"}
EXCLUDE_FILES = {"CLAUDE.md", "AGENTS.md", "README_PACK.md", "START_PROMPT.md", "verify_no_cloud.py", "package-lock.json"}
EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".toml", ".txt", ".yml", ".yaml", ".example", ".cfg", ".ini", ".html", ".md"}
# Docs may *mention* banned names (e.g. "we do NOT use OpenAI") but code/config may not.
# HARVEY_NOTES.md documents the one-time purge of the upstream fork, including the banned names.
DOCS_ALLOWED = {"COST_STATEMENT.md", "MODELS_AND_LICENCES.md", "PRD.md", "WORKFLOWS.md", "TASKS.md",
                "ACCEPTANCE_CHECKLIST.md", "ARCHITECTURE.md", "KNOWN_LIMITATIONS.md", "README.md",
                "HARVEY_NOTES.md"}
pat = re.compile("|".join(BANNED), re.I)
hits = []
for p in ROOT.rglob("*"):
    if not p.is_file() or any(part in EXCLUDE_DIRS for part in p.parts) or p.name in EXCLUDE_FILES:
        continue
    if p.suffix.lower() not in EXTS and not p.name.startswith(".env"):
        continue
    if p.suffix == ".md" and p.name in DOCS_ALLOWED:
        continue
    for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
        if pat.search(line):
            hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
llm = ROOT / "app" / "llm_client.py"
if llm.exists():
    for u in re.findall(r"https?://[^\s\"']+", llm.read_text()):
        if not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")):
            hits.append(f"app/llm_client.py: non-local URL {u}")
if hits:
    print("FAIL: cloud-AI references found:\n" + "\n".join(hits)); sys.exit(1)
print("PASS: no cloud-AI references; llm_client is local-only.")
