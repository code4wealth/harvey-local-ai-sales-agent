# Build Plan

## Phase 2 review checkpoint — 2026-11-22

This checkpoint records the Phase 2 scope approved for this branch; the broader phase headings below are the original project build plan.

- **Implemented:** `app/text_clean.py` strips complete, lone-closing, and unclosed Qwen-style reasoning markers before downstream parsing; the client requests `think: false` but also checks/cleans raw replies. `num_predict` defaults to 1500 and can be overridden per call.
- **Implemented:** inference logs retain `eval_count`, wall latency, and tokens/second when Ollama provides `eval_duration`; existing databases are migrated additively.
- **Implemented:** live Ollama smoke harness and script-generated transcript; the latest sandbox attempt is recorded as `BLOCKED` because `127.0.0.1:11434` refused the connection. No Qwen inference was performed.
- **Implemented:** fictional SAMPLE corpus with two products, 25 prospect pages, 20 labelled replies, and a 13/7 development/held-out split. No reply-classification accuracy is reported because the classifier/evaluator is not implemented.
- **Verified:** official Hugging Face model card lists `all-MiniLM-L6-v2` as Apache-2.0; existing installed runtime metadata is documented in `docs/MODELS_AND_LICENCES.md`.
- **Blocked:** do not add `sentence-transformers` or PyTorch until the installed-metadata audit covers the actual CPU-only dependency set. The PyPI Torch wheels available to this sandbox declare CUDA dependencies; the CPU wheel distribution is not accessible through the permitted package-download hosts.
- **Not implemented:** model fetcher, local embeddings module, and network-disabled model inference test. Those require the dependency gate and an available model artifact.

This is a partial review checkpoint, not a claim that all Phase 2 acceptance criteria have passed.

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

- [x] Add two products' company information labelled `SAMPLE`.
- [x] Add 20–30 prospects and local page text, clearly labelled.
- [x] Add 15–20 labelled sample replies (13 development, 7 held out).

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
