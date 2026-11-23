# Build Plan

Target: 48–72h. Deterministic work in this patch is kept separate from LLM
workflow/prompt work. See `docs/WORKFLOWS.md` for the detailed data contract.

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
- [x] Add `scripts/smoke_embeddings.py` for first download and later `HF_HUB_OFFLINE=1` checks (script implementation tested with the test-only model stub)
- [x] Real embeddings smoke passed online and offline on Windows, Python 3.12.16; offline run used `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, with Wi-Fi on for both runs (operator-provided output: `test_evidence/real_run/smoke_embeddings.txt`)
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
- [x] Future LLM output schemas are flat, with lists of flat objects at most; no LLM prompts/workflows were started (documented contract)

## Deferred — intentionally not started

The operator will tune prompts against real `qwen3:4b` output before these
workflows begin. Do not implement them as part of the current deterministic
patch.

- [ ] Business profile, ICP generation, prospect research summaries, signal classification prompts, problem statement, email generation, and reply classification
- [ ] LLM workflow schemas, retry policy beyond the existing client contract, and pipeline orchestration
- [ ] Reply-evaluation script and sample replies

## Remaining project work

- [ ] Add labelled sample company information, prospects/page text, and replies (all sample data must be labelled)
- [ ] Complete PRD API endpoints and dashboard screens
- [ ] Add full offline test, network proof, Ollama-stop/drain proof, and save test evidence
- [ ] Finish hardware, offline, failure-handling, cost, and known-limitations documentation; verify model/dependency licence metadata before release
- [ ] Prepare demo video and release checklist
