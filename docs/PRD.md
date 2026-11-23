PRD — Harvey Local Multi-Product AI Sales Agent
1. Objective

Fork ethanplusai/harvey and extend it into a multi-product AI sales agent that runs entirely locally with zero LLM cost: Ollama + Qwen3 (or another permissively licensed open-weight model), SQLite, Python, FastAPI, Harvey's frontend or React, sentence-transformers, and Scrapy/BS4/Playwright for public-web research only.

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
F4	Prospect import (CSV) + local page data; optional online research	20–30 prospects loaded; research module isolated
F5	Prospect research from downloaded data	Summary per prospect + embedding similarity to ICP
F6	Buying-signal classification	Typed signals with verified evidence quotes + confidence
F7	Problem statement generation	2–3 sentences tied to signals and product pain points
F8	Prospect scoring & prioritisation	Hybrid deterministic score + breakdown; sorted table
F9	Personalised email generation	<120 words, one CTA, no invented facts
F10	Reply classification	8 labels + confidence + next action; accuracy table on sample replies
F11	Hardware detection + model recommendation	RAM/CPU/GPU detected; tiers documented
F12	Failure handling	Banner, queue, worker retry, non-LLM features keep working
F13	Traceability	inference_log page with model, host, tokens, latency, timestamp
F14	Full pipeline run per product	One click runs steps 2–9 with per-step status
5. Non-functional requirements
Reliability: JSON validation + retries; timeouts; graceful errors.
Reproducibility: single setup path (README), pinned dependencies.
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

data/company_info/*.md (2 products), product-scoped prospect CSVs, data/prospect_pages/*.txt, and a 60-row `data/sample/replies.csv` containing only reply IDs and text. Optional reply labels are operator-authored separately under `data/sample/reply_labels.csv`; signal-evaluation labels live under `data/eval/`.

8. Scoring formula

score = 0.35*icp_similarity*100 + 0.35*signal_score + 0.15*size_fit + 0.15*title_fit, breakdown stored. Deterministic.

9. Deliverables

Working app, forked repo, 5–10 min demo (incl. offline test), docs (architecture, models/licences, hardware, offline, failure handling, cost statement, known limitations), test evidence.

10. Automatic-failure checklist (must all be false)

Paid/cloud LLM dependency · silent cloud fallback · hidden paid API · no local-inference proof · mocked agent presented as real · hard-coded outputs as intelligence · missing offline test.

11. Out of scope

Actually sending emails, CRM integrations, paid enrichment, multi-user auth.
