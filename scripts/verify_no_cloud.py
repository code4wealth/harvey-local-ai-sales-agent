#!/usr/bin/env python3
"""Fail if cloud-AI SDKs, domains, or keys appear in the repo. Run before every commit.

Two pattern classes:
  BRAND_PATTERNS  - names of cloud-AI products/vendors. Allowed docs (DOCS_ALLOWED,
                    exact repo-relative paths) may mention these, e.g. to say
                    "we do NOT use them".
  SECRET_PATTERNS - API keys / private keys. These are scanned EVERYWHERE,
                    including the allowed docs.
"""
import re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
BRAND_PATTERNS = [
    r"\bopenai\b", r"\banthropic\b", r"google[-_.]generativeai", r"\bgemini\b", r"\bcodex\b",
    r"api\.openai\.com", r"api\.anthropic\.com", r"generativelanguage\.googleapis\.com",
    r"\bgroq\b", r"together\.ai", r"api\.cohere", r"api\.mistral\.ai", r"openrouter",
    r"\bclaude\b",
]
SECRET_PATTERNS = [
    r"OPENAI_API_KEY", r"ANTHROPIC_API_KEY", r"GEMINI_API_KEY",
    r"sk-[A-Za-z0-9_-]{16,}", r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
    r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}",
]
BANNED = BRAND_PATTERNS + SECRET_PATTERNS
EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".claude", "test_evidence", "dist", "build"}
EXCLUDE_FILES = {"CLAUDE.md", "AGENTS.md", "README_PACK.md", "START_PROMPT.md", "verify_no_cloud.py", "package-lock.json"}
EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".toml", ".txt", ".yml", ".yaml", ".example", ".cfg", ".ini", ".html", ".md"}
# Docs that are allowed to *mention* the brand names (never secrets). Exact
# repo-relative POSIX paths, not globs. HARVEY_NOTES.md documents the one-time
# purge of the upstream fork, so it necessarily lists the removed names.
DOCS_ALLOWED = {
    "README.md",
    "docs/PRD.md", "docs/WORKFLOWS.md", "docs/TASKS.md",
    "docs/ARCHITECTURE.md", "docs/ACCEPTANCE_CHECKLIST.md",
    "docs/COST_STATEMENT.md", "docs/MODELS_AND_LICENCES.md", "docs/KNOWN_LIMITATIONS.md",
    "docs/HARVEY_NOTES.md",
}
brand = re.compile("|".join(BRAND_PATTERNS), re.I)
secret = re.compile("|".join(SECRET_PATTERNS), re.I)
pat = re.compile("|".join(BANNED), re.I)
hits = []
for p in ROOT.rglob("*"):
    if not p.is_file() or any(part in EXCLUDE_DIRS for part in p.parts) or p.name in EXCLUDE_FILES:
        continue
    if p.suffix.lower() not in EXTS and not p.name.startswith(".env"):
        continue
    rel = p.relative_to(ROOT).as_posix()
    allowed_doc = rel in DOCS_ALLOWED
    for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
        if allowed_doc:
            if secret.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:120]}")
        elif pat.search(line):
            hits.append(f"{rel}:{i}: {line.strip()[:120]}")
llm = ROOT / "app" / "llm_client.py"
if llm.exists():
    for u in re.findall(r"https?://[^\s\"']+", llm.read_text()):
        if not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")):
            hits.append(f"app/llm_client.py: non-local URL {u}")
if hits:
    print("FAIL: cloud-AI references found:\n" + "\n".join(hits)); sys.exit(1)
print("PASS: no cloud-AI references; llm_client is local-only.")
