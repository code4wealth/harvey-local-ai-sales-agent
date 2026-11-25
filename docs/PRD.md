PRD — Harvey Local Multi-Product AI Sales Agent
1. Objective

Fork ethanplusai/harvey and extend it into a multi-product AI sales agent that runs locally with zero paid LLM inference: Ollama + Qwen3 (or another appropriately licensed open-weight model), SQLite, Python, FastAPI, React, and sentence-transformers. In this implementation, optional public-page collection is a separate `requests` + BeautifulSoup script that reads operator-supplied URLs; Scrapy and Playwright are not used (see `docs/KNOWN_LIMITATIONS.md`).

2. Hard constraints (non-negotiable)
No OpenAI / Anthropic / Gemini / Codex / any paid LLM API, cloud inference, paid agent platform, paid enrichment API, or per-token service.
No silent fallback to cloud. If Ollama is down: clear error, deterministic features still work, AI tasks queue.
After install + model download, all AI workflows work with internet disabled.
External web research must be separated from local AI inference.
No hard-coded outputs presented as generated intelligence. Mocked/sample data must be labelled.
Secrets outside source code; no AI keys exist at all.
3. Users & value

Primary user: a founder/SDR who wants to sell several products, each with its own ICP, prospects, signals, scoring and outreach, privately and for free on a laptop.

4. Functional requirements
ID	Requirement	Acceptance
F1	Product/company configuration (multiple products, each with docs)	Create/edit/list products; docs stored locally
F2	Business profile generation from local company info	JSON profile saved; regenerable
F3	Product-specific ICP generation	Different products give different ICPs
F4	Prospect import (CSV) + local page data; optional online research	CSV and saved page text work offline; optional URL-CSV fetch helper is separate from inference and observes robots.txt
F5	Prospect research from downloaded data	Summary per prospect + embedding similarity to ICP
F6	Buying-signal classification	Typed signals with verified evidence quotes + confidence
F7	Problem statement generation	Persist a conservative one- or two-sentence statement grounded in the product profile, ICP, and verified prospect signals; skip model inference when evidence is missing
F8	Prospect scoring & prioritisation	Deterministic product-specific ranking + component explanations and missing-input reporting
F9	Personalised email draft	Grounded draft from stored product profile and verified signals; persisted, never sent
F10	Reply classification	8 labels + confidence + rationale; separately measured on the 36-reply development split
F11	Hardware detection + model recommendation	RAM/CPU/GPU detected; tiers documented
F12	Failure handling	Banner, queue, worker retry, non-LLM features keep working
F13	Traceability	inference_log page with model, host, tokens, latency, timestamp
F14	Full pipeline run per product	One click runs steps 2–9 with per-step status
5. Non-functional requirements
Reliability: JSON validation + retries; timeouts; graceful errors.
Reproducibility: setup path is in README; the frontend has a lockfile, while Python dependencies currently use bounded version ranges rather than a complete exact lock.
Privacy: no telemetry; only localhost for AI.
Performance: laptop tier (qwen3:4b) completes one prospect end-to-end in a reasonable time; pipeline shows progress.
Licences: every model/library/major dependency documented with exact licence.
6. Hardware tiers
Tier	Condition	Model
high-performance	VRAM ≥12 GB or RAM ≥32 GB	qwen3:14b
standard-plus	VRAM ≥6 GB or RAM ≥16 GB	qwen3:8b
standard-laptop	RAM ≥8 GB	qwen3:4b
low-resource	else	qwen3:1.7b
7. Data (SAMPLE, clearly labelled)

data/company_info/*.md (2 fictional products), product-scoped prospect CSVs, data/prospect_pages/*.txt, and a 60-row `data/sample/replies.csv` containing only reply IDs and text. Reply labels are isolated under `data/eval/reply_labels.csv`; they are not imported into the app database or passed to the classifier. Signal-evaluation labels also live under `data/eval/`.

8. Scoring formula

score = 0.35*icp_similarity*100 + 0.35*signal_score + 0.15*size_fit + 0.15*title_fit, breakdown stored. Deterministic.

9. Deliverables

Working app, forked repo, 5–10 min demo (incl. offline test), docs (architecture, models/licences, hardware, offline, failure handling, cost statement, known limitations), test evidence.

10. Automatic-failure checklist (must all be false)

Paid/cloud LLM dependency · silent cloud fallback · hidden paid API · no local-inference proof · mocked agent presented as real · hard-coded outputs as intelligence · missing offline test.

11. Out of scope

Actually sending emails, CRM integrations, paid enrichment, multi-user auth.
