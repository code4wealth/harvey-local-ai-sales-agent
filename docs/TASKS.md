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
[ ] db.py schema (all tables) + helpers
[ ] llm_client.py (generate, generate_json, ollama_up, OllamaUnavailable, inference logging, think:false, <think> stripping)
[ ] hardware.py + GET /api/hardware, GET /api/status
[ ] queue_worker.py (background retry)
[ ] Tests: client with mocked httpx (down/up/invalid JSON), hardware tiers, queue
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
