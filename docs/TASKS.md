# Build Plan

## Phase 0 — Reconnaissance and setup (0–4h)

- [ ] Fork/clone Harvey, run it, and document its structure in `docs/HARVEY_NOTES.md`.
- [ ] Install Ollama, pull `qwen3:4b` (and `qwen3:8b` if possible), create a virtual environment, and pin dependencies.
- [x] Search tracked text for inference-provider references and record file/line findings in `docs/dev/HARVEY_NOTES.md`.
- [x] Add the no-cloud verifier, `Makefile`, and key-free local `.env.example` from the approved context pack.

## Phase 1 — Local-inference foundation and legacy purge (4–6h)

- [x] Add the local Ollama client, hardware detection, SQLite foundation, task queue/worker, and mocked-HTTP tests.
- [x] Remove old provider runtimes, references, credentials/configuration, dependencies, and provider setup.
- [x] `make verify` passes against the cleaned repository.

## Phase 2 — Core workflows (6–14h)

- [ ] Add the remaining database tables and helpers.
- [ ] Implement validated profile, ICP, research, signals, problem, scoring, email-draft, and reply workflows.
- [ ] Implement the deterministic scorer and unit tests.
- [ ] Review and obtain approval for the license of `sentence-transformers` and every transitive dependency before adding it.

## Phase 3 — Sample data (14–18h)

- [ ] Add two products' company information labelled `SAMPLE`.
- [ ] Add 20–30 prospects and local page text, clearly labelled.
- [ ] Add 15–20 labelled sample replies.

## Phase 4 — Workflows and pipeline (18–32h)

- [ ] Add Pydantic schemas and tests for each model output and deterministic component.
- [ ] Add a resumable pipeline with per-step status and product-scoped persistence.
- [ ] Add reply evaluation with accuracy and confusion-table output.

## Phase 5 — API and failure handling (32–38h)

- [ ] Add PRD API endpoints with a consistent error format.
- [ ] Expose local server/model status, queued tasks, and helpful missing-model instructions.

## Phase 6 — Dashboard (38–48h)

- [ ] Show Ollama status, hardware tier, recommended model, and a local-inference status label.
- [ ] Add product setup, profile/ICP views, prospect table/detail, reply classification, inference log, and queue views.
- [ ] Label sample data visibly in the UI.

## Phase 7 — Proof and offline acceptance (48–60h)

- [ ] Add `scripts/offline_test.py` and run all eight workflows with offline model-cache settings.
- [ ] Record network proof showing the AI endpoint is only `127.0.0.1:11434`.
- [ ] Test Ollama stop/start, clear error, queue, and queue drain.
- [ ] Save logs/screenshots to `test_evidence/`.

## Phase 8 — Docs and release (60–72h)

- [ ] Verify model/library licenses; write models/licenses, hardware, offline, failure, cost, and limitations docs.
- [ ] Prepare a 5–10 minute demo and verify the exact release tag.
