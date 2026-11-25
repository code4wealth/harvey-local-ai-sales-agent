# Build Plan

This checklist began as the original implementation plan. The current
repository status is summarized first; historical completed phases below are
retained as context. See `docs/WORKFLOWS.md` for detailed data contracts.

## Current status

- [x] Local-only profile, ICP, and buying-signal workflows with deterministic
  Ollama settings and bounded validation retries.
- [x] Reply classification with isolated labels and a development/held-out
  evaluator; held-out runs require a frozen matching prompt hash.
- [x] Product-scoped deterministic prospect ranking.
- [x] Evidence-grounded unsent draft workflow; no verified signals means a
  persisted `no verified evidence` skip.
- [ ] Run the exact commands in `docs/DEMO.md` with local Ollama and fill in
  the `RESULT: fill after live run` placeholders. No live run is claimed.
- [ ] Optionally run held-out evaluation only after reviewing/freezing the
  prompt; this roadmap has not performed held-out evaluation.
- [x] Evidence-grounded problem statements and a persistent product-level
  pipeline run from the `/operations` workflow console with per-step progress;
  the React workspace remains available at `/`.

## Phase 0 — Recon and setup

- [x] Fork/clone Harvey and document upstream structure in `docs/HARVEY_NOTES.md` (deterministic repo work)
- [x] Review cloud-AI references and add the strict `scripts/verify_no_cloud.py` guard (deterministic)
- [x] Add `Makefile`, `.env.example`, and local setup docs (deterministic)
- [x] Ollama installed and `qwen3:4b` smoke call completed on the target machine (real Gate 1 below)

## Phase 1 — Local-only inference boundary

- [x] Remove cloud-AI dependencies and paths; all AI calls go through `app/llm_client.py` to loopback (deterministic)
- [x] `make verify` passes (deterministic)

## Phase 2 — Core backend and Ollama contract

- [x] SQLite base schema, inference logging, and persistent queue helpers (deterministic)
- [x] Local Ollama client, JSON validation/retry, typed failures, and `think:false` (mocked HTTP transport)
- [x] Hardware/status API and queue-worker lifecycle/retries (mocked Ollama transport)
- [x] Replace the Ollama-running-sensitive test with a real-transport closed ephemeral-port test; no skip based on the user's running server (deterministic test)
- [x] Test `ReadTimeout` on `/api/tags`: queue worker remains alive and `/api/status` returns HTTP 200 with slow/model-busy state; probe default is 5 seconds (mocked HTTP transport)
- [x] Add nullable `inference_log.load_seconds`; convert Ollama `load_duration` nanoseconds to seconds, preserve `null` when omitted, and migrate existing databases (mocked Ollama responses + SQLite migration tests)
- [x] Remove Docker files; README is the single setup path (deterministic)
- [x] `make verify` passed before the Patch 2.2 first commit (mocked tests plus local closed-port transport test)

### Real Gate 1 evidence

- [x] smoke test (real), 1 call, Windows, qwen3:4b, Ollama 0.40.17
- Warm run: `1.7107742` seconds / `27` eval tokens (from `test_evidence/real_run/smoke_ollama.txt`)
- cold first call, from operator terminal, not in evidence file: `9.1278431` seconds / `26` eval tokens

## Phase 3 — Data model and deterministic batch

- [x] Product/prospect SQLite schema, employee-count and page-embedding fields with legacy migration; nullable/partial score storage migration (deterministic)
- [x] Product create/list, product-scoped CSV import, prospect listing/detail, and local UTF-8 page-text storage/loading; no URL fetching (deterministic)
- [x] Atomic CSV import with validated optional fields and local page-path containment (deterministic)
- [x] Add production `app/embeddings.py` using cached local `all-MiniLM-L6-v2`; vector BLOB encoding is versioned; unit tests use a test-only model stub (mocked)
- [x] Add `scripts/smoke_embeddings.py` to report the cached local model's sequence limit and vector dimension (script implementation tested with the test-only model stub)
- [x] Historical operator-reported embeddings smoke on Windows, Python 3.12.16; the reported offline run used `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, with Wi-Fi on for both runs (`test_evidence/real_run/smoke_embeddings.txt`). Current code always forces both offline flags before loading; this historical smoke was not rerun for the current task.
- [x] Quote verification normalizes NFKC, straightens curly quotes/dashes, collapses whitespace, lowercases, requires at least 8 normalized characters and 2 words, retains only normalized source substrings, and returns the drop count (deterministic)
- [x] Excel CSV files open as `utf-8-sig`; row errors are reported before any insert, and the import is atomic (deterministic)
- [x] Prospect page loading rejects absolute paths and `..` components on both POSIX and Windows; local files stay under `data/prospect_pages/` (deterministic)
- [x] `icp_similarity`: cosine mapped linearly from 0.15–0.65 to 0–1 and clamped (deterministic)
- [x] `signal_score`: each type once, highest confidence per type, weighted sum capped at 100 (deterministic)
- [x] `size_fit`: 100 in range; logarithmic decay to zero at 3× outside the range (deterministic)
- [x] `title_fit`: decision-maker 100, influencer 60, other 20 using ICP buyer-title keywords (deterministic)
- [x] Missing components stay `null`, contribute zero, are named in `missing_components`, and set `partial`; totals never re-normalize (deterministic)
- [x] `size_fit` returns safely for `min=0`, missing bounds, and `max < min` (deterministic)
- [x] Unknown queue task types fail visibly with a terminal failed state and are never marked done (deterministic)
- [x] Deterministic CSV-import and scoring queue handlers run without Ollama and are not starved by queued LLM tasks (mocked Ollama health failure)
- [x] Workflow schemas are flat with Pydantic validation; profile, ICP, signal, reply-classification, and unsent-draft workflows use bounded retries and persist outcomes

## Remaining project work

- [x] Add fictional SAMPLE product information, product-scoped prospects/page text, and text-only replies; keep reply labels isolated in `data/eval/`.
- [x] Implement validated local profile, ICP, signal, reply-classification, and outreach-draft workflows with persistent outage replay.
- [x] Implement deterministic product-specific ranking and expose ranking/draft APIs.
- [x] Add a reply evaluator with redacted reports, prompt freezing, and a held-out gate.
- [ ] Run full live Ollama demos and record actual results; do not substitute mocked results.
- [ ] Run the network-isolation and Ollama-stop/drain demonstrations on the target machine.
- [x] Problem-statement generation and full pipeline orchestration are implemented with persistent per-step status, retry, and resume behavior.
- [ ] Review model/dependency licence metadata and complete release checklist before release.
