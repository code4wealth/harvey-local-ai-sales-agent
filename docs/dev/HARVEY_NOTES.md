# Phase 0 — Harvey repository reconnaissance

**Status:** Phase 0 reconnaissance complete; implementation direction approved and underway.

**Repository snapshot:** `b212385259da92246a56311d790d936e75dd70dd` on `arena/d5cb361d-harvey-local-ai-sales-agent`.

**Phase 0 checkpoint:** At the end of reconnaissance, this notes file was the only workspace change. No application code, configuration, tests, dependencies, or data had been changed, and no tests had been run. Subsequent implementation is tracked separately below.

## Executive assessment

This checkout is not a small, untouched Harvey starter. It is a mature **Sellbird 0.4.0** checkout, the renamed successor to Harvey. The active application is `sellbird/`; the `harvey/` package is only a compatibility shim that forwards old commands to Sellbird. The current implementation is an outreach platform that can discover prospects, use a subscription-backed model, draft and send email, read replies, and operate a dashboard.

It does **not** currently satisfy the assignment's central local-inference rule:

- The inference abstraction is `sellbird/brain.py`, which launches either the Claude Code CLI or the Codex app-server CLI. Both use hosted model services and subscriptions, not Ollama.
- `sellbird/integrations/quota.py` also reads the Claude OAuth usage endpoint directly. There is no `app/llm_client.py`, Ollama client, Qwen model configuration, hardware recommender, local embedding path, AI task queue, or target `inference_log` table.
- `Brain.think_json` produces an untyped `dict | list | None`; it does not validate each workflow result against a dedicated Pydantic response model. There are some retries for provider/process errors and for specific trainer operations, but invalid model JSON is not uniformly schema-validated and retried.
- If the current provider is unavailable, `sellbird/main.py` preflights it and skips the whole heartbeat. That is not the target behavior of keeping deterministic features usable and queuing AI-only tasks. Separately, Scout falls back to heuristic scoring when a model call fails, and the trainer supplies fixed ICP defaults when extraction fails. Those are existing fallback behaviors, not Ollama behavior; they should be replaced by deterministic scoring plus explicit queue/error handling, not carried over as generated intelligence.
- The current product includes live email sending/reading and multiple external research, verification, warmup, and enrichment integrations. The assignment explicitly excludes actually sending email and paid enrichment; this functionality should not accidentally remain active in the target app.

The target architecture and product documents included in the task message are the applicable requirements for Phase 0. On disk, however, the checked-in `CLAUDE.md` is Sellbird's old operator/setup guide; `AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOWS.md`, `docs/TASKS.md`, and `docs/ACCEPTANCE_CHECKLIST.md` are **missing**. The existing `docs/how-it-works.md` and other docs describe Sellbird, not the local multi-product assignment.

## 1. Repository facts

### Top-level structure and entry points

- **Python project:** `pyproject.toml`, `requirements.txt`; Python `>=3.11`.
- **Active package:** `sellbird/` (agents, collectors, integrations, models, dashboard, state, CLI, prompts/skills support).
- **Legacy package:** `harvey/` (`harvey` CLI and `python -m harvey` shim only).
- **Runtime entry points:** the `sellbird` console script and `python -m sellbird` enter `sellbird.cli`; `sellbird.main.heartbeat()` is the orchestration loop. `sellbird.dashboard` defines the FastAPI dashboard/API.
- **Frontend:** `sellbird/web/` is static HTML/CSS/vanilla JavaScript, served by FastAPI; no React/Vite build. The dashboard binds to loopback (`127.0.0.1:5555`) and has host/token protections.
- **Persistence:** `sellbird/state.py` owns a large, versioned SQLite schema and async data-access layer; it uses `aiosqlite`. `sellbird/storage.py` also provides a pluggable storage-backend seam, so the current persistence architecture is broader than the requested local SQLite-only database.
- **Prompt/content files:** `prompts/` and `skills/` contain Sellbird's system, agent, and sales-playbook text.
- **Tests:** 275 tracked files total, 206 Python files, and 118 top-level test modules. The existing tests cover many Sellbird integrations and provider-specific behavior; they are not an offline Ollama acceptance suite.
- **No target data tree:** no tracked `data/`, `app/`, `frontend/`, or `test_evidence/` directory. No `Makefile`, `scripts/verify_no_cloud.py`, `scripts/offline_test.py`, or `scripts/eval_replies.py` is present. `scripts/` currently contains only `diagnose_overpass.py`.

### Stack and licensing

- Existing Python dependencies include FastAPI/Uvicorn, Pydantic v2, HTTPX, BeautifulSoup, Playwright, `aiosqlite`, and other Sellbird mail/storage/security integrations. The package already has FastAPI and HTTPX, but it does not include an Ollama-specific dependency, sentence-transformers, Scrapy, or an inference SDK.
- The app has no OpenAI or Anthropic Python SDK dependency. That does **not** make inference local: it delegates to externally authenticated CLI programs. CI installs `@openai/codex` for a provider-surface test.
- `.env.example` contains mail, web research, contact-verification, and service API settings, but no LLM API-key variables. The model auth path is instead through local Claude/Codex CLI login state. Several non-LLM service keys are for paid or account-based research/enrichment and are outside the assignment's desired scope.
- `LICENSE` identifies the current Sellbird release as **AGPL-3.0-only**. `NOTICE` says earlier Harvey releases (through 0.3.x) remain MIT-licensed. This is a relevant fork/licensing difference to resolve/document before submission; the repo does not currently contain the requested dependency/model-license table.
- No Qwen3, `all-MiniLM-L6-v2`, Ollama setup, offline test evidence, or sample prospect/page/reply dataset is present.

## 2. Current architecture and inference/data flow

1. **Configuration:** `sellbird/config.py` defines a single `ProductConfig`, one `ICPConfig`, and a `BrainConfig` selecting `claude` or `codex`. `sellbird.yaml` is a single-product template. There is no product ID or multi-product database relation.
2. **Inference:** agent/workflow code builds prompts and calls `Brain.think` / `Brain.think_json`. `sellbird/brain.py` selects Claude or Codex and handles process timeouts, retries, response parsing, and existing usage-event records. Claude process isolation is in `sellbird/claude_runtime.py`; Codex protocol, authentication snapshots, model catalog, and quota support are in `sellbird/codex.py`. `Brain` also accepts an arbitrary `transport` seam. There is no fixed local-only inference boundary.
3. **AI-producing call sites:**
   - Business/product training and ICP extraction: `sellbird/trainer.py` (`_extract_product_info`, `_extract_icp`, competitive information, objections).
   - Interactive setup test: `sellbird/setup.py`.
   - Prospect scoring/personalization: `sellbird/agents/scout.py`.
   - Email generation/sequence repair: `sellbird/agents/writer.py` and `sellbird/humanize.py`.
   - Reply classification and drafted replies: `sellbird/agents/handler.py`.
   - Offer suggestions: `sellbird/offer.py`.
   - Exact call sites: `trainer.py:652,705,746,792`; `setup.py:179`; `offer.py:91`; `humanize.py:126`; `scout.py:1286`; `writer.py:614,716,806`; `handler.py:1350,1550,1595`. All are caller-side work; after approval they must route through the one permitted client.
4. **Research:** `sellbird/collectors/discover.py`, `sellbird/collectors/profile.py`, `sellbird/agents/scout.py`, `sellbird/collectors/ats.py`, and related integrations perform public-web search/scraping and contact enrichment. Some routes require external APIs or paid services. The boundary between research and the model is not represented by a separate `app/research/` package, and sample local pages are absent.
5. **Scoring/signals:** `sellbird/fit.py` computes a deterministic company fit score with a different current weighting (sector 20, decision-maker 30, reachability 25, buying 25). `sellbird/agents/scout.py` also lets a model change prospect scores, with a heuristic fallback. `sellbird/signals.py` contains a governed signal catalog and `state.py` stores observations. This is useful source material, but it is not the required product-specific `0.35/0.35/0.15/0.15` scorer, and the target's verified evidence-quote contract is not implemented as stated.
6. **Database and failure handling:** `sellbird/state.py` includes companies, prospects, campaigns, conversations, outbox, settings, observations, runs, and usage tables. `usage_events` stores model/provider/token/duration information, but it is not the target `inference_log` (e.g. no inference host field). There is no `task_queue` for AI work. The existing outbox is for **outgoing email**, not queued model tasks.
7. **Pipeline:** `sellbird.main.heartbeat()` coordinates prospecting, writing, sending, reply handling, and analysis. `sellbird/pipeline.py` is a DISCOVER → PROFILE pipeline, not a full product-specific workflow runner with per-step profile/ICP/research/signals/problem/score/email/reply status.
8. **Dashboard:** `sellbird/dashboard.py` has extensive JSON routes and the local static UI; its surface is tightly coupled to sending, inboxes, provider quotas, and Sellbird-specific entities. Its screens/styles may be useful references, but the target API and many displayed product claims need to be rebuilt or pruned.

## 3. Mapping to the requested target layout

| Target module/area | Closest existing code | Phase 0 assessment / proposed treatment |
|---|---|---|
| `app/main.py` and API routes | `sellbird/dashboard.py`, `sellbird/main.py`, `sellbird/cli.py` | There is a FastAPI app, but it is a dashboard API coupled to a separate email-agent heartbeat. Create the target API surface around the requested product workflows; reuse only suitable auth/route patterns. |
| `app/llm_client.py` | `sellbird/brain.py`, `sellbird/claude_runtime.py`, `sellbird/codex.py`, `sellbird/integrations/quota.py` | No compliant client exists. Replace provider selection, CLI subprocesses, account/quota logic, and the arbitrary transport bypass with one Ollama-only client at `http://127.0.0.1:11434`. Preserve useful timeout/retry concepts only; use `OllamaUnavailable`, no cloud fallback, structured validation, and task logging/queue semantics. |
| `app/hardware.py` | None | New module required for RAM/CPU/GPU detection and the requested model-tier recommendation. |
| `app/db.py` | `sellbird/state.py`, `sellbird/storage.py` | Existing schema/migration practices are useful; current schema is oversized for this assignment, async, provider-branded, and has no products/task queue/inference log. Build the target schema, preferably using the specified stdlib `sqlite3` unless a deviation is approved. |
| `app/queue_worker.py` | None | No AI task queue/worker exists. Do not mistake the email `outbox` for one. Add an explicit retryable task queue for AI jobs while keeping deterministic operations available. |
| `app/embeddings.py` | None; `sellbird/fit.py` is heuristic scoring only | Local embeddings are not implemented. The requested sentence-transformers/model dependency is absent; before adding it, verify package/model licensing and ask for approval as required by the project rules. |
| `app/scoring.py` | `sellbird/fit.py`; heuristic and model scoring in `sellbird/agents/scout.py` | Retain the deterministic-scoring concept, but implement the required weighted formula and product context. The model must not alter the numeric score. |
| `workflows/profile.py`, `workflows/icp.py` | `sellbird/trainer.py`, `sellbird/config.py` | Training has product/ICP extraction, but it is a website trainer for one product with generic JSON and fixed fallback defaults. Split the workflows, bind each result to a product, validate Pydantic outputs, and queue failures rather than persisting invented defaults. |
| `workflows/research.py`, `research/` | `sellbird/collectors/profile.py`, `collectors/discover.py`, `agents/scout.py`, `collectors/ats.py` | There is substantial web research/scraping to mine, but it is interwoven with online discovery/enrichment and agent work. Isolate public-web code in `app/research/`, use local SAMPLE files for offline acceptance, and exclude paid enrichment services. |
| `workflows/signals.py` | `sellbird/signals.py`, `site_facts.py`, `collectors/ats.py`, Scout | The catalog/observation model is a useful starting point. Add the required evidence quote and source-text verification, scoped per product; reject unverified quotes. |
| `workflows/problem.py` | No dedicated equivalent; pieces are in Writer prompts/facts | New workflow required for a 2–3 sentence problem statement grounded in verified research/signals. |
| `workflows/email.py`, `workflows/reply.py` | `sellbird/agents/writer.py`, `agents/handler.py`, `humanize.py`, prompt files | They contain useful prompt/rule ideas, but currently depend on hosted-provider Brain calls and extensive send/inbox behavior. Rebuild the workflow boundary and keep generated copy local; actual email sending is explicitly out of scope. |
| `workflows/pipeline.py` | `sellbird/main.py`, `sellbird/pipeline.py` | Existing heartbeat and discover/profile runner are not the target full workflow. Add a product-scoped orchestrator with persisted per-step states and clear partial-failure handling. |
| `frontend/` | `sellbird/web/` + `sellbird/dashboard.py` | Existing static JS/CSS/HTML means a no-build UI is possible and avoids adding a frontend dependency. Reuse visual patterns selectively; remove email, CRM, paid-provider and subscription-quota panels. |
| `data/` | None | Add only explicitly labelled SAMPLE company docs, prospect CSV, page text, and labelled replies as specified. No live or guessed intelligence should be introduced as sample data. |
| `scripts/`, `tests/`, `test_evidence/` | `scripts/diagnose_overpass.py`; large Sellbird-specific test suite | The required verifier, offline pipeline, reply evaluation, Make target, and evidence folder are missing. Add focused local-only tests/scripts; retire provider-specific tests after replacing their coverage with local HTTP/Ollama mocks. |
| `docs/` | Existing Sellbird product/deployment docs | Required target architecture/workflow/task/acceptance/deliverable docs are absent. The current docs need replacement or careful pruning after approval; they describe subscription inference, paid services, and actual email sending. |

## 4. Concrete assignment gaps and reuse candidates

### Hard gaps / risks

- **No single local inference boundary:** `sellbird/brain.py` has two external providers plus a pluggable transport. The current quota reader also makes an external provider-specific request. A new `app/llm_client.py` must be the only inference path.
- **No offline proof:** there is no `offline_test.py`, `verify_no_cloud.py`, `eval_replies.py`, `test_evidence/`, or `make verify`. Current CI/test design is centered on old providers and their CLI surfaces.
- **No product isolation:** product and ICP are singleton configuration sections. Current prospects/companies/campaigns are not keyed to multiple product-specific contexts.
- **No task queue / correct logs:** current usage accounting is tied to provider subscriptions and lacks the target inference host/task-queue contract. Existing mail outbox is a different subsystem.
- **Unsafe fallbacks for this specification:** Scout's model-based scoring and model-unavailable heuristic fallback conflict with the target scoring rule; trainer's fallback ICP defaults are literal generated-looking values. Use deterministic score code and queue failed generated-output work instead.
- **No workflow schemas/evidence verification:** current model output parsing is generic; the target requires Pydantic schemas/retries and evidence quotes checked against source text.
- **Out-of-scope surface:** current email sending/reading, paid discovery/enrichment/verification, warmup, and provider setup dominate the product. The new assignment should not call those services or send messages.
- **No hardware/embedding implementation or sample corpus.**
- **Privacy wording is misleading for the target:** although the current application process and SQLite database are local, its model prompts go through hosted services. Target docs/UI must state the Ollama-only behavior and local boundary accurately.

### Reuse candidates

- Python 3.11+ packaging, Pydantic v2, FastAPI, HTTPX, BeautifulSoup/Playwright, and the existing dashboard's static asset serving.
- Pydantic domain-model style (`sellbird/models/`) and the database's migration/idempotency conventions, after trimming the data model to the required product scope.
- Public web parsing/HTTP hardening and provenance/observation concepts in `collectors/`, `public_http.py`, `signals.py`, and `state.py`, after moving research into its own module and removing paid enrichment.
- Deterministic company-fit logic from `sellbird/fit.py` as a design starting point, not as the final formula.
- Safety rules, opt-out/anti-fabrication concepts, email style checks, and clear operation/error messaging. The email-sending implementation itself is not needed for this assignment.

## 5. Cloud-AI reference audit (exact file:line inventory)

The following index was produced by scanning **tracked text files at the snapshot commit** (excluding binary images/fonts) for provider/product terms including Anthropic, Claude, OpenAI, Codex, ChatGPT/GPT model IDs, Gemini, Cohere, Mistral, Groq, Hugging Face, Ollama, Bedrock, Vertex AI, and other common model names. Line numbers are 1-based; adjacent matches are compressed as ranges. This is deliberately broader than active inference code: it includes docs, tests, negative-test strings, crawler user-agent strings, and historical changelog entries so each occurrence can be reviewed. No Ollama/Qwen implementation was found.

The inventory itself necessarily mentions providers to document the existing state. It is a **Phase 0 development note**, not runtime code; resolve whether to remove this note or explicitly exclude this audit from the eventual verifier before final submission. Do not claim a blanket zero-string scan while retaining this inventory unchanged.

### Tracked app/config/build/docs references

```text
.github/ISSUE_TEMPLATE/bug_report.yml: 38
.github/workflows/tests.yml: 1-4, 35, 40, 43, 45-46
.gitignore: 41-42
CHANGELOG.md: 43-44, 117, 586, 735, 780, 839, 857-859, 861-862, 864-868, 870, 872, 874-875, 880-881, 890, 897, 910, 913, 986, 1029
CLAUDE.md: 3, 5, 29, 53, 55, 293, 328, 342, 344, 351, 371, 391-392
CONTRIBUTING.md: 4
Dockerfile: 9, 41, 45, 48
README.md: 10, 73, 77, 90, 94, 99, 102, 183
SUPPORT.md: 3-4
docker-compose.yml: 21, 23-24
docs/approval-and-sending.md: 7
docs/codex.md: 1, 3, 5, 8-9, 12, 16-17, 23-32
docs/configuration.md: 18-20, 34, 38, 50, 62, 140-141
docs/dashboard.md: 36
docs/docker.md: 19-20, 34, 45
docs/how-it-works.md: 7, 9, 17, 25, 56-58, 85
docs/troubleshooting.md: 13, 17, 25
pyproject.toml: 12
sellbird.yaml: 105
sellbird/__init__.py: 1
sellbird/agents/scout.py: 3, 5, 916, 994, 1240, 1242, 1291, 1312
sellbird/agents/sender.py: 898
sellbird/agents/writer.py: 84, 225, 891
sellbird/brain.py: 3-5, 29, 37, 43, 50-51, 53, 57, 73, 101, 115, 120, 127-129, 132, 158-159, 162, 165, 169-171, 175, 180-182, 187, 192, 210-212, 214, 218, 226-228, 297-298, 303, 306, 308-310, 318, 336, 340, 342, 355, 375, 384, 389-390, 414, 423, 445, 454-455, 461, 463, 469, 474, 476, 478, 482, 484-485, 494, 497, 501, 505, 512, 517-518, 529-530, 603, 669-670, 677, 734
sellbird/claude_runtime.py: 1-2, 6, 9, 11, 20, 24, 31, 58-59, 61-67, 77-78, 85-86, 89-90, 94-97, 111, 117, 123-124, 126, 129, 143-145, 155, 172, 197, 221, 241-242, 244, 246-248, 256-257, 261-264
sellbird/cli.py: 180, 240-241, 292-293, 310, 315, 317, 349-353, 359, 368-369, 371-372, 386, 578, 1154-1155, 1160, 1178-1179, 1254, 1302, 1310-1311
sellbird/codex.py: 1, 3-5, 10, 13-14, 18-19, 25, 40-41, 44, 64, 68-70, 75, 84-87, 91-93, 95-96, 99, 104, 107, 157, 170, 191, 193, 217-218, 227, 239-240, 251-252, 255-257, 264, 273-275, 278, 281-282, 286, 288-289, 297, 303-304, 321, 324, 328-330, 336-337, 348, 362-363, 365, 375-380, 391, 396, 402, 404-405, 407-408, 412, 414, 416, 418, 421, 429, 446, 495, 516-518, 526, 541, 543-544, 582, 584, 586, 597, 612-613, 621-622, 657, 664, 737, 742-743, 751, 767-768, 775, 789-790, 815, 817, 824, 844, 846, 878, 883, 905-906, 910, 912, 914-915, 918-919, 946-947, 949-950, 952, 969, 971, 974, 977-978, 984, 990-991, 997, 1000, 1008, 1014, 1017-1018, 1022, 1048, 1078-1079, 1119, 1121, 1126, 1137, 1139, 1143, 1145, 1162-1163, 1177-1178, 1187, 1216, 1220-1221, 1224, 1227, 1233-1234, 1237-1238, 1243, 1248, 1256, 1262, 1271, 1273, 1278-1279, 1287, 1290, 1294, 1301, 1303, 1311-1312, 1319, 1345, 1363-1364, 1385-1386, 1393, 1395-1396, 1408, 1424, 1430, 1434, 1437-1438, 1441-1442, 1532-1533, 1535, 1555-1556
sellbird/collectors/profile.py: 110-111
sellbird/config.py: 275, 680, 684, 688, 699-700, 710-711, 713, 716, 718, 723, 743, 746, 753, 755, 964
sellbird/dashboard.py: 306, 315, 896, 900, 1059, 1062-1063, 1071-1072, 1103, 1106-1107, 1117-1120, 1122-1125, 2429
sellbird/humanize.py: 4, 31
sellbird/integrations/quota.py: 1, 3-4, 21, 25, 31-32, 42, 51, 53, 56, 65-66, 77-78, 100, 109, 135, 164, 173
sellbird/main.py: 163, 322, 368, 385, 389, 416, 439
sellbird/mcp_install.py: 1, 9, 13-17, 41-42, 44-45, 47-50, 52-53, 57-58, 80, 114, 126, 128-129, 132, 135, 141, 149, 158, 160, 162, 165-171, 173, 176, 178-182, 184, 187-188, 191, 193-197, 199, 202-203, 205-210, 213, 218, 226, 237, 245-246, 261, 265, 273, 276, 283, 297, 309-311, 313, 316-317, 319, 322, 324, 327-329, 331, 333-334, 337, 339, 342, 346, 349, 353, 359, 388, 419, 440, 465-466, 468, 470, 505, 516, 522, 526-527, 542, 544-546, 554, 562-563, 572, 574, 588-590, 593, 596, 599
sellbird/mcp_server.py: 246
sellbird/pipeline.py: 69
sellbird/setup.py: 167-169, 172-174, 177-178, 187, 189-190, 192-194, 197, 200, 202-205, 208, 299-300, 302, 304-307, 311-313, 318, 322, 326-327, 333-335, 338-339, 343-345, 349, 352, 357, 361, 368, 372, 376, 627, 645, 647, 691, 930-932
sellbird/state.py: 236, 503, 505-506, 509, 511, 563-564, 2610, 2621, 2653, 2784, 2788, 2805-2806, 2809
sellbird/trainer.py: 399, 458, 621, 656, 1006
sellbird/usage.py: 3-4, 7, 9, 22-24, 27
sellbird/web/app.js: 1482, 1487, 1490-1491, 1493, 1515-1516, 1521, 1524-1526, 1612, 1615
sellbird/web/index.html: 323, 509, 521, 591-592, 596-597
sellbird/workspace_home.py: 115, 119-120
skills/email_frameworks.md: 147
```

### Test, fixture, and provider-negative-test references

```text
tests/conftest.py: 3-5, 7, 20, 22, 27, 41-43, 45, 47-48, 50, 58
tests/fake_anthropic.py: 1-2, 4
tests/fake_codex.py: 1, 3, 20, 22, 38-39, 53, 58, 70, 77-78, 81, 85, 99, 105, 107-108, 113, 124-126, 182, 210, 231, 257, 260, 265, 267, 271, 274-275, 282-283, 330
tests/fixtures/pre_codex_harvey_0_2_1.sql: 1-2, 177, 181
tests/test_brain_no_tools.py: 1, 3, 6, 20, 26, 64, 80, 92-93, 108-109, 111-114, 120, 124, 140, 146, 149, 154, 159, 164, 176, 185, 189, 202-203, 207-209, 222, 292, 295-299, 302
tests/test_brain_provider.py: 1, 19, 32, 34-35, 50-51, 56-59, 68-72, 76, 104, 107, 109-110, 112, 116, 118, 120, 125, 136, 139, 165-167, 172-174, 176-177, 180-181, 184-185, 187, 190, 194-195, 200-201, 203-204, 208, 210-211, 213, 215, 220-221, 224, 231, 233-234, 238, 242, 244, 250-254, 256, 261-262, 265, 270-271, 273, 277-278, 284, 286, 298-299, 314, 317, 334, 339, 346, 360, 367-369, 372, 374, 384, 386, 388, 390, 393-394, 413, 415, 419, 423, 440-444, 448, 454, 465, 469, 475, 480, 484, 487-490, 495, 498-499, 502-503, 534, 537-539, 541, 543, 545, 548, 551-552, 555, 557, 560, 564-567, 570, 573-574, 579-580, 583, 585, 587, 618-619, 621, 625, 651-653, 655, 661, 666, 669, 676-677, 679, 682-683, 685-686, 691, 696-697, 702, 707, 711, 718, 720, 722-723, 726, 730-732, 737-738, 742, 748, 751-753
tests/test_claude_cli_isolation.py: 1, 4, 6-8, 11, 15-16, 38, 43-45, 49, 51, 53-56, 81, 83, 88, 90, 95-99, 112, 117-119, 122, 164-165, 175, 196, 200-202, 204
tests/test_codex.py: 1, 3, 5, 21, 23, 25, 27, 38, 46, 68, 76, 82, 112, 128, 183, 195-197, 200-205, 224, 228, 238, 253, 263, 270, 273, 286, 296, 298, 301, 307-308, 312, 324, 338, 348, 353, 362-363, 373-374, 378, 390, 393, 400-401, 403, 412, 419, 436-437, 447, 480, 497, 506, 532, 547, 566, 595, 601, 609, 614, 626, 638, 643, 695-696, 701-702, 704-705, 709, 711-713, 715, 718-720, 727, 729, 735, 742-743, 746, 750-751, 756-759, 761, 776-777, 780, 787, 802-803, 811, 817-819, 822-825, 830, 836, 851, 853, 874, 891
tests/test_codex_cli_surface.py: 1, 3, 5, 9, 12, 14, 32, 35, 37, 58-60, 69, 75, 120, 128-130, 136, 147, 158, 161, 186, 189, 192-193, 203, 206-208, 210, 214, 220, 223, 225, 232, 245, 247, 255, 258-260, 324-326, 329-331, 336, 342-343, 349-350, 355-356, 366, 369-370, 376-377, 381, 393, 395-396, 403, 411, 419-420, 422, 424-425, 427-428, 432, 437-441
tests/test_codex_e2e.py: 1-2, 7, 9, 23, 25, 27, 33, 36, 49, 59, 62, 64, 78-79, 84, 87-88, 161, 170, 174, 225, 228-229, 231, 242, 246, 255, 282, 304, 326, 385, 418, 424-425, 427, 432, 434, 439, 448, 453, 458, 460-462, 464, 467-468, 470, 502, 598, 748
tests/test_codex_platform.py: 1, 8-11, 24-25, 30, 38, 63, 71-72, 75, 81-82, 92, 100-101, 105, 107, 110, 125, 131, 134, 138-140, 155, 164, 168, 175, 186-187, 190
tests/test_codex_soak.py: 1-2, 23, 25, 27, 31, 33, 41, 63-64, 88-90, 94, 136, 190, 192
tests/test_config_extra.py: 97, 103, 130, 133
tests/test_dashboard_pipeline.py: 53, 56, 59
tests/test_dashboard_usage_date.py: 22, 36-37
tests/test_discover.py: 1429
tests/test_docker_config.py: 48, 60
tests/test_gmail_history.py: 237, 239
tests/test_gmail_inbox.py: 60, 62-63, 129-130
tests/test_gmail_send_outcomes.py: 19, 129-130, 158-159
tests/test_humanize.py: 90
tests/test_mcp_install.py: 3-5, 26, 28, 32, 42-44, 50, 64, 66-67, 71, 81-82, 86, 91, 94, 100, 102, 104, 106, 113-114, 116-118, 121-122, 126, 128, 132, 138, 141, 149-150, 153-154, 156, 158, 161, 166, 170-171, 174, 179, 182-183, 186-187, 196-197, 200-201, 204, 210-211, 213-214, 217, 221, 232-234, 236, 238-241, 244, 250, 252, 263, 265, 286, 289, 295-296, 299-300, 302, 305-306, 308, 312, 314, 319-320, 324, 329, 351, 353-354, 365-366, 369-370, 376-378, 381, 385, 390, 394-396, 398, 402-403, 406, 410, 414-415, 421, 423, 427-428, 430, 435-438, 441, 444, 449, 451-453, 457, 462, 464, 466-467, 470-472, 476, 481-482, 486, 489, 508, 511, 519, 521, 528, 536, 538, 542, 548, 552, 562-564, 567, 569, 571, 573, 575, 581, 585, 589, 618, 622, 650, 658-659, 669, 671, 683, 689, 712, 715-717, 719
tests/test_packaging.py: 8, 22, 26, 38, 62, 65, 76, 82, 91, 95, 100, 121
tests/test_send_window.py: 736, 878
tests/test_sending_held.py: 177
tests/test_setup_precleared.py: 486
tests/test_trainer_config.py: 34, 37, 64, 67, 111, 114-115
tests/test_trulyinbox.py: 228
tests/test_usage.py: 32, 49, 53, 57, 71, 75, 94, 99, 110, 137, 143, 153
tests/test_windows_support.py: 1-2, 13-14, 70, 73, 76, 85-87, 94-97, 99, 107-110, 116, 118-121, 124-126, 130-132, 135-137, 141-143, 163-165, 168, 202-210, 213-214, 221, 224, 228-232
tests/test_writer_min_score.py: 6
tests/test_writer_retry.py: 5, 88, 120, 161-162, 185
```

### Removal/replacement proposals by category

1. **Inference runtime:** retire `sellbird/brain.py`'s Claude/Codex provider selection and transport seam; remove the two provider runtimes and provider quota reader. Replace all model work with one fixed-host `app/llm_client.py` using only local Ollama. Model-down behavior should be `OllamaUnavailable` + queued task + clear UI/API status, never a provider fallback.
2. **Config, storage, UI, setup:** remove subscription provider/model selection, Claude/Codex login/quota flows, quota percentages, and provider-specific status fields. Replace with selected local model/hardware recommendation, task status, and `inference_log` data (including the fixed host, model, token counts, latency, timestamp). Remove the MCP installer/server integration and its dependency if no target feature needs it.
3. **Training/workflows:** route each call site listed above through the client. Replace literal trainer fallback ICP values with validated result/error/queue state. Keep scoring deterministic and independent of Ollama. Validate every JSON output with a workflow-specific Pydantic model and bounded retries.
4. **Research-only vendor strings:** `sellbird/collectors/profile.py:110-111` contains vendor-specific crawler user-agent names (not model inference). To satisfy a strict zero-provider-reference scan, remove those names or drop that vendor-specific portion of the crawler-blocking signal; do not confuse it with inference code.
5. **Build and dependencies:** remove the external CLI install from `Dockerfile`, the home-directory auth mount from Compose, the Codex install/test from GitHub Actions, and stale package metadata/issue-template options. Keep only normal Python dependencies needed by the new app; document any model/library licenses and ask before adding dependencies.
6. **Docs, UI copy, and skills:** replace subscription/cloud-cost/setup instructions with the local Ollama install/model-download/offline/failure story. The current changelog contains historical provider material; either trim/rewrite it for the deliverable or clearly resolve its presence with the final verification policy. Update the Sellbird-branded readme/docs and no-send/out-of-scope statements.
7. **Tests and fixtures:** delete/replace provider runtime tests/fakes and historic provider fixtures with local HTTP mocking, Ollama-unavailable queue/retry tests, strict endpoint-allowlist tests, and schema/evidence tests. Some occurrences are only negative tests (e.g. testing an unsupported provider name or ensuring inherited provider variables are not passed); replace their assertions with generic forbidden-provider checks. `tests/test_discover.py:1429` references a documentation filename, not an inference provider, but would also need review under a literal text scan.

## 6. Deviations / decisions proposed for approval

1. **Follow the requested `app/` target layout** rather than expanding the legacy `sellbird/` package in place. Reuse selected parser, schema-migration, security, and UI patterns only; remove old product surface from the shipped target. This is the cleanest way to make the Ollama-only boundary auditable.
2. **Keep a no-build static frontend** unless you ask for React/Vite. The existing UI is vanilla HTML/CSS/JS and the assignment permits Harvey's existing frontend; this avoids adding a frontend dependency and keeps the setup path reproducible.
3. **Use the target's simple local SQLite schema**, not Sellbird's storage plugin or mail/CRM schema. The repo currently uses `aiosqlite`; the target calls for stdlib `sqlite3`, so I recommend following the target rather than adding or retaining an async database dependency without need.
4. **Make online research optional and isolated.** Reuse public-site parsers where useful, but rely on labelled local SAMPLE inputs for the acceptance/offline run and remove paid search/enrichment paths. No live email sends, inbox polling, or CRM integration should be brought into the target app.
5. **No dependency is proposed for addition in Phase 0.** Sentence-transformers is absent and has a significant transitive footprint; if it is needed for the requested embeddings, first verify the exact library/model licenses and request approval before modifying the dependency set.
6. **Preserve this reconnaissance note only as a temporary development artifact.** It contains the provider names needed to meet the Phase 0 audit request. Before final submission, either delete it after approval or explicitly exclude it from the final source scan as a non-shipped audit; otherwise a literal repository-wide zero-provider scan will correctly flag it.

## 7. Initial next-phase proposal (superseded by the approved two-commit plan below)

At the end of Phase 0, `docs/TASKS.md` was missing, so there was no checked-in phase checklist to tick. The following was the initial proposal before the user approved the target layout and two-commit plan:

1. **Local foundation:** create the focused `app/` package and tests; implement the only local inference client, hardware/model recommendation, SQLite products/task queue/inference log, explicit Ollama-down errors, and the no-cloud verification guard.
2. **Data and research:** add product-local company info and clearly labelled sample prospects/pages/replies; isolate public-web research; build offline-safe embedding setup only after dependency/license approval.
3. **Workflows and pipeline:** add Pydantic output schemas and validated profile, ICP, research, signal (evidence verification), problem, email, and reply flows; implement the required deterministic scorer; persist product-scoped status and retry queued model tasks.
4. **API and dashboard:** wire the multi-product experience to the new API, label all sample data in the UI, and show Ollama availability, queued tasks, and inference traceability. Do not ship email sending or cloud-provider surfaces.
5. **Acceptance/evidence/docs:** add `verify_no_cloud.py`, the end-to-end offline test, reply evaluation, `make verify`, test evidence, architecture/failure/offline/licensing/hardware/cost/limitations docs, then run the full acceptance suite.

## 8. Approved implementation plan and lineage

The user approved the `app/` layout and a two-commit implementation sequence: (1) add the local inference, hardware, SQLite, queue, and focused tests; (2) remove the legacy Sellbird implementation, tests, MCP installer, and Docker/provider CI setup. Run `make verify` and tests after each commit, and stop after the second validation. No email sending, paid research, or trainer defaults are in scope. `psutil` is the only newly approved dependency; sentence-transformers is deferred until Phase 2 pending a license and transitive-license review.

The local repository is shallow/grafted at `b212385259da92246a56311d790d936e75dd70dd`; its configured `origin` is `https://github.com/code4wealth/harvey-local-ai-sales-agent.git`. The current baseline is Sellbird 0.4.0 and carries AGPL-3.0-only. The remote `ethanplusai/harvey` v0.3.0 tag (`e2632eb20ee2d4fb6fe04ae715a52f578acf9a37`) exists and its `LICENSE` and project metadata identify MIT. The current baseline is tagged locally as `legacy-sellbird`. The rebuilt, newly authored app code will carry MIT; no AGPL-licensed 0.4.0 implementation is being copied into it. Preserve the MIT notice and keep the old AGPL baseline identifiable by its tag.

The sole newly approved foundation dependency, `psutil`, declares BSD-3-Clause on PyPI (verified against its package metadata; version 7.2.2 at implementation time). No other new dependency has been added. `sentence-transformers` and its transitive licenses remain deferred for Phase 2 review.
