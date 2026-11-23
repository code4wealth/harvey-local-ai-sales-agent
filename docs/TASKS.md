Build Plan (tick as you go). Target: 48-72h.
Phase 0 - Recon & setup (0-4h)
[x] Fork+clone Harvey; run it; document its structure in docs/HARVEY_NOTES.md
[ ] Install Ollama; pull qwen3:4b (and 8b if possible); create venv; pin deps  (venv done; Ollama install is on the target machine — no network/host for it in this sandbox)
[x] Grep every cloud-AI reference (code, deps, env, docs); list them
[x] Add scripts/verify_no_cloud.py, Makefile, .env.example from this pack
Phase 1 - Purge cloud AI (4-6h)
[x] Remove/replace all cloud SDKs, keys, calls; update requirements/package.json
[x] make verify passes
Phase 2 - Core backend (6-14h)
[x] db.py schema (all tables, including pipeline status) + logging/queue helpers
[x] llm_client.py (local chat, JSON validation/retry, typed failures, status logging, think:false) (mocked)
[x] hardware.py + GET /api/hardware, GET /api/status (mocked Ollama transport; hardware tiering uses explicit test values)
[x] queue_worker.py (lifespan background thread, crash recovery, retry/max-attempt handling) (mocked)
[x] HTTPX MockTransport client/queue/API tests and pure hardware tiers (mocked)
[x] Unmocked localhost-down OllamaUnavailable regression test (skips if a local Ollama server is running)
[x] scripts/smoke_ollama.py created with nested-schema check; target-machine run pending
Phase 2.1 - Ollama contract patch
[x] Add temperature 0.2, configurable num_ctx, context-warning log, and hardware-tier context recommendation (mocked)
[x] Distinguish OllamaUnavailable from OllamaTimeout; queue retries both; status reports slow vs unavailable (mocked)
[x] Add inference_log status and legacy-schema migration; best-effort error logging (mocked)
[x] Retry JSON with previous validation error; nested smoke schema; environment URL guard test (mocked)
[x] Remove Docker files; README is the single setup path
[ ] Run `ollama --version`, then `ollama pull qwen3:4b && python scripts/smoke_ollama.py` on target machine and review output
Phase 3 - Sample data (14-18h)
[ ] 2 products' company_info (labelled SAMPLE)
[ ] 20-30 prospects + page texts (from public pages while online, or labelled samples)
[ ] 15-20 labelled replies
Phase 4 - Workflows (18-32h)
[ ] profile, icp, research (+embeddings.py), signals (+evidence verify), problem, scoring, email, reply
[ ] Pydantic schemas + unit tests for deterministic parts
[ ] pipeline.py orchestrator + /api/pipeline/run/{id}
[ ] scripts/eval_replies.py
Phase 5 - API & failure handling (32-38h)
[ ] All endpoints from the PRD; consistent error format
[ ] Ollama-down banner data, queue endpoint, model-missing hint
Phase 6 - Dashboard (38-48h)
[ ] Status bar (Ollama, model, tier, "AI: local [ok]")
[ ] Product setup, profile/ICP view, prospect table by score, prospect detail, reply classifier, inference log, queue view
Phase 7 - Proof & offline (48-60h)
[ ] scripts/offline_test.py (HF_HUB_OFFLINE=1) - runs all 8 workflows
[ ] Network proof: lsof -i/ss during run shows only 127.0.0.1:11434
[ ] Ollama-stop test: error + queue + drain
[ ] Save logs/screenshots to test_evidence/
Phase 8 - Docs, video, release (60-72h)
[ ] README, MODELS_AND_LICENCES (verify against real LICENSE/model cards), HARDWARE, OFFLINE_TEST, FAILURE_HANDLING, COST_STATEMENT, KNOWN_LIMITATIONS
[ ] Demo video 5-10 min (script in ACCEPTANCE_CHECKLIST)
[ ] Tag v1.0; demo that exact tag; check links are public
