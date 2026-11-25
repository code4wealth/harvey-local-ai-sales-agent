# HARVEY_NOTES.md — Phase 0 recon of this fork (ethanplusai/harvey, a.k.a. Sellbird)

Base commit: `b212385259da92246a56311d790d936e75dd70dd` (branch `arena/83834673-harvey-local-ai-sales-agent`)
Date: 2026-11-23 · Status: recon only, **no code changed yet**

## 1. What this repo actually is

Harvey was renamed **Sellbird** (`sellbird/` package; `harvey/` is now a thin
compatibility shim). It is **not** a cloud-SDK app: it does all of its "thinking"
by **shelling out to the operator's Claude Code CLI** (default) or **Codex CLI**
(ChatGPT subscription). There is no LLM SDK in `requirements.txt`/`pyproject.toml`.
The relevant stack facts:

| Aspect | Finding |
|---|---|
| Language / entry | Python 3.11+, `sellbird` console script (`sellbird/cli.py`), `python -m sellbird` |
| Web framework | FastAPI + uvicorn (dashboard served by `sellbird/dashboard.py`, ~3000 lines) |
| Frontend | **No React/Vite.** Vanilla HTML/CSS/JS in `sellbird/web/` (index.html 613 l, app.js 3,367 l, app.css 1,179 l), vendored fonts. Served as static files by FastAPI. |
| Database | SQLite via **aiosqlite**, WAL mode, linear idempotent migrations via `PRAGMA user_version` (`sellbird/state.py`, `sellbird/storage.py`). DB at `data/sellbird.db`. |
| "Brain" (LLM path) | `sellbird/brain.py` → either `sellbird/claude_runtime.py` (Claude Code CLI subprocess, JSON mode via `--output-format json`) or `sellbird/codex.py` (isolated Codex runtime, ~1,561 lines). Usage/quota accounting: `sellbird/usage.py`, `sellbird/integrations/quota.py` (calls `api.anthropic.com/api/oauth/usage` with the operator's OAuth token). |
| Agents | `sellbird/agents/{scout,writer,handler,sender,analyst}.py` — async classes called by the heartbeat (`sellbird/main.py`) and `sellbird/pipeline.py`. Prompts in `prompts/*.md`, knowledge in `skills/*.md`. |
| Research | `sellbird/collectors/` (ATS, discover via OpenStreetMap, people/profile scrapers), `sellbird/signals.py` (page fetch + signal detection, mostly **no-LLM** HTTP+regex), `sellbird/site_facts.py`. Playwright is listed as a dependency. |
| Sending / CRM | Gmail, Microsoft 365, SMTP integrations, outbox, approval flow, deliverability — **all out of scope** for the assignment (PRD §11). |
| Tests | pytest; 150 test files; `tests/conftest.py` stubs the `claude` CLI. CI (`.github/workflows/tests.yml`) installs `@openai/codex` for one test job. |
| Licence | **AGPL-3.0-only** (`LICENSE`, `pyproject.toml`). Notice/attribution must be kept in any derivative. |
| Size | ~275 files, ~38k LOC Python + ~5k LOC web assets. |

## 2. Mapping Harvey modules → target layout (CLAUDE.md)

| Target (pack) | Harvey today | Reuse decision |
|---|---|---|
| `app/main.py` (FastAPI) | `sellbird/dashboard.py` (routes + static mount), `sellbird/main.py` (heartbeat) | **Pattern reused, code not portable** — routes are bound to the old data model and old agents. New `app/main.py` from scratch; keep the "static vanilla-JS dashboard, no build step" approach. |
| `app/llm_client.py` (Ollama @ 127.0.0.1:11434, only AI path) | `sellbird/brain.py` + `claude_runtime.py` + `codex.py` | **Replace entirely.** New client: `httpx` → `POST /api/generate` & `/api/tags`, `think:false`, `<think>` stripping, pydantic-validated `generate_json`, retries, per-call `inference_log` rows, `OllamaUnavailable`. |
| `app/hardware.py` | — (nothing; Harvey assumes a subscription plan) | **New.** RAM/CPU/GPU detect → qwen3 tier recommendation (PRD §6). |
| `app/db.py` (sqlite3 stdlib) | `sellbird/state.py` (aiosqlite + migrations) | **Rewrite sync** with stdlib `sqlite3` per pack; new schema: products, business_profiles, icps, prospects, signals, problem_statements, scores, emails, replies, inference_log, task_queue. |
| `app/queue_worker.py` | — (Harvey pauses and waits) | **New.** Background poll of `task_queue`; drains when Ollama returns. |
| `app/embeddings.py` | — | **New.** sentence-transformers `all-MiniLM-L6-v2`, offline-safe (local cache / HF_HUB_OFFLINE). |
| `app/scoring.py` | `sellbird/fit.py` + `sellbird/signals.py` scoring parts | **Rewrite** to PRD §8 formula; deterministic; Harvey's fit score is ICP-keyword based, not the required 0.35/0.35/0.15/0.15 blend. |
| `app/workflows/{profile,icp,research,signals,problem,email,reply,pipeline}.py` | `sellbird/agents/{scout,writer,handler,sender,analyst}.py`, `prompts/*.md`, `skills/*.md` | **Rewrite as small sync functions** matching the pack's 8-workflow table. Old prompts are Claude-subscription-specific and far too long for qwen3:4b; new short prompts + JSON examples are required. `skills/` knowledge files are generic sales copy — optional style reference only. |
| `app/research/` (web scraping, non-AI) | `sellbird/collectors/*`, `sellbird/signals.py`, `sellbird/public_http.py` | **Port the idea, not the modules** — pack wants isolated `app/research/` (BS4/Scrapy/Playwright). Sample pages ship in `data/prospect_pages/` so the demo works offline without scraping. |
| `frontend/` dashboard | `sellbird/web/*` | **New, Harvey-styled**: keep the visual language (fonts already vendored in repo), new screens: status bar, products, profile/ICP, prospect table, prospect detail, reply classifier, inference log, queue. |
| `data/` SAMPLE | — (Harvey ships no sample DB) | **New**: `data/company_info/`, product-scoped prospect CSVs, fictional `data/prospect_pages/*.txt`, `data/sample/replies.csv` (60 text-only rows), and isolated evaluator annotations under `data/eval/`. |
| `tests/` | 150 test files, all coupled to Claude/Codex stubbing | **Replace** with new suite (llm_client with mocked httpx, hardware tiers, scoring, evidence verification, pipeline with mocked LLM). |
| `scripts/verify_no_cloud.py`, `Makefile`, `scripts/offline_test.py`, `scripts/eval_replies.py` | — | **New**, from the pack. |
| Docs | `docs/*.md` are Sellbird docs | Keep as `docs/legacy-sellbird/` reference or delete (see plan); write new deliverable docs. |

## 3. Cloud-AI reference inventory (why verify_no_cloud can't pass as-is)

Excluding `.git`: **1,710 matches** across ~90 files. Code/config runtime paths (all
must be deleted or rewritten — the verify regex bans the words everywhere outside
`DOCS_ALLOWED` markdown and the excluded dirs):

| File:line (sample) | References |
|---|---|
| `sellbird/codex.py` | 210 matches — entire Codex runtime (`sellbird/codex.py:1` header through EOF); `USAGE_URL`-style endpoints, `codex login`, ChatGPT plan catalog |
| `sellbird/brain.py:1`, `sellbird/brain.py:36` (`PROVIDER_LABELS = {"claude": ...}`), `think_json`, `is_within_budget` | 83 — provider selection, usage-limit pauses |
| `sellbird/claude_runtime.py:85-97`, `:123-130`, `:247` | 52 — Claude CLI discovery (`find_claude`, `@anthropic-ai/claude-code` paths, install hints) |
| `sellbird/mcp_install.py` | 124 — installs `@anthropic-ai/claude-code` MCP shim |
| `sellbird/mcp_server.py:1` | 1 + MCP server exposing Sellbird tools to the Claude CLI |
| `sellbird/integrations/quota.py:4,21,25,42,56,66,173` | 20 — calls `https://api.anthropic.com/api/oauth/usage` with operator OAuth |
| `sellbird/usage.py` | 8 — `claude_config_dir()`, plan/quota accounting |
| `sellbird/cli.py` | 29 — `claude`/`codex` login/setup flows |
| `sellbird/setup.py` | 57 — onboarding around Claude/Codex login |
| `sellbird/config.py` | 17 — `brain.provider`, `max_daily_claude_percent`, etc. |
| `sellbird/state.py` | 16 — `provider="claude"` usage rows |
| `sellbird/dashboard.py:592`-adjacent web FAQ + 21 code matches | 21 + `sellbird/web/index.html:592,597`, `sellbird/web/app.js:1482-1525` |
| `sellbird/agents/*.py` (scout 8, writer 3, sender 1), `sellbird/pipeline.py:1`, `sellbird/main.py:7`, `sellbird/trainer.py`, `sellbird/humanize.py`, `sellbird/collectors/profile.py`, `sellbird/workspace_home.py`, `sellbird/__init__.py` | provider labels & prompt plumbing |
| `sellbird.yaml` (`max_daily_claude_percent: 80`), `sellbird/mcp_install.py`, `.github/workflows/tests.yml:45-46` (`npm install -g @openai/codex`), `Dockerfile:45-48` (installs Claude Code, runs `check_cli`), `docker-compose.yml`, `.gitignore` (`.claude/`), `pyproject.toml` (keyword `claude`), `tests/fake_anthropic.py`, `tests/fake_codex.py`, `tests/conftest.py` | config/CI/Docker |
| `tests/` | ~700 matches across ~35 files (`test_brain_provider.py` 183, `test_mcp_install.py` 176, `test_codex*.py`, `test_claude_cli_isolation.py`, `fake_*`) |
| Docs/README | `README.md` (8), `docs/codex.md` (17), `docs/configuration.md`, `docs/troubleshooting.md`, `docs/how-it-works.md`, `docs/docker.md`, `docs/dashboard.md`, `docs/approval-and-sending.md`, `CONTRIBUTING.md`, `CHANGELOG.md` (29, historical — keep as history or purge), `SUPPORT.md`, `.github/ISSUE_TEMPLATE/bug_report.yml` |

**No paid/cloud *SDK* exists in dependencies** — the violation is the subscription-CLI
architecture itself, which the assignment forbids in any form ("no paid LLM API …
no per-token service"; the shipped app must have zero Claude/Anthropic/OpenAI references).

## 4. Proposed deviations from the pack's target layout (with reasons)

1. **Delete the legacy `sellbird/` runtime instead of porting it.** The pack's verify
   guard bans the *words* claude/codex/anthropic everywhere outside excluded dirs and
   allowed docs — that rules out "keep but exclude". Porting 38k LOC of
   subscription-agent code to Ollama would be a rewrite anyway; the PRD's out-of-scope
   list (sending, CRM, auth) removes most of it. Git history preserves Harvey; new
   README keeps attribution + AGPL licence and links to the upstream project.
2. **Keep Harvey's dashboard approach (FastAPI + static vanilla JS, vendored fonts)**
   rather than introducing React+Vite, which would add node_modules and a build step
   for no benefit at this scope. The new `frontend/` is a fresh, smaller dashboard.
3. **SQLite stays stdlib `sqlite3`** (pack rule) even though Harvey used aiosqlite —
   simpler, sync, fine for one-user laptop scale.
4. **Scrapy is not used**; BeautifulSoup + httpx (already deps) cover the one optional
   "online research" path, and sample pages make scraping optional and offline-safe.
   Licence table will list bs4 (MIT), httpx (BSD), Playwright (Apache-2.0, optional).
5. **Keep `prompts/`/`skills/` only as deleted or moved to `legacy/`** — see plan;
   final tree has none of it if we delete legacy wholesale.
6. Harvey's own `docs/` (Sellbird product docs) and brand assets are **removed or
   archived to `docs/legacy/`** but would trip the scan; cleanest is deletion since
   they describe a product we no longer ship. `CHANGELOG.md` rewritten from scratch;
   attribution goes in `NOTICE`/`README.md` (both AGPL-relevant).

## 5. Risks / environment facts

- **No Ollama in this sandbox** and no outbound host for it (allowed: github.com,
  codeload.github.com, api.github.com, registry.npmjs.org, pypi.org, files.pythonhosted.org).
  We can `pip install` everything from PyPI, but **cannot run a real model here**.
  All LLM tests must mock httpx; `offline_test.py` and the demo are to be run on the
  user's machine (or wherever Ollama is installed). qwen3:4b is ~2.5 GB download.
- This sandbox: Python 3.11.2, 2 CPUs, 3.8 GB RAM — fine for building/tests, not for inference.
- `sentence-transformers` pulls torch (~2 GB) — heavy but on PyPI; it is needed for
  F5 similarity. If install proves too heavy it stays a required dep with offline
  model cache, per pack.
- AGPL-3.0: derivative keeps the same licence; keep `NOTICE` and attribution.
- `.env.example` currently contains Gmail/SMTP etc. keys → replaced by the pack's version.

## 6. What Phase 1+ will do (see plan in chat)

See the accompanying message: recommended approach is a clean rebuild in `app/` +
`frontend/` + `data/` + new `docs/` deliverables, with the legacy Sellbird tree
removed, verify guard active from the first commit, then Phases 2–8 from docs/TASKS.md.
