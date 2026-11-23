# AGENTS.md — Agent roles & rules (for Claude Code subagents or any coding agent)

Shared hard rules: see CLAUDE.md ("THE ONE RULE"). All agents obey them.

Runtime agents (inside the app) — each is a function in app/workflows/
Agent	File	Input	Output (JSON schema)	LLM?
Business Profiler	profile.py	company docs	summary, value_proposition, key_features[], pain_points_solved[], differentiators[]	yes
ICP Generator	icp.py	profile	industries[], company_size, buyer_titles[], pain_points[], trigger_events[], disqualifiers[]	yes
Prospect Researcher	research.py	prospect page text	summary, what_they_do, size_hint, tech, recent_news[]	yes + embeddings
Signal Classifier	signals.py	page text + ICP	signals[{type, evidence, confidence}]	yes + code verification
Problem Writer	problem.py	profile, research, signals	2–3 sentence problem statement	yes
Scorer	scoring.py	similarity, signals, size, title	score 0–100 + breakdown	NO (deterministic)
Email Writer	email.py	profile, research, signals, problem	{subject, body} <120 words, 1 CTA	yes
Reply Classifier	reply.py	reply text	{label, confidence, next_action}	yes
Orchestrator	pipeline.py	product_id	runs all above in order, per-step status	n/a

Each agent: build prompt → llm_client.generate_json(...) → validate with pydantic → save to SQLite → return. No agent may call the network or any model except through llm_client.

Development subagents (suggested for Claude Code)
architect — reads Harvey repo, maps it to target layout, proposes changes. Read-only.
cloud-purger — finds and removes every cloud-AI dependency (code, deps, env, docs). Runs verify_no_cloud.py.
backend-builder — llm_client, hardware, db, queue, API routes, with tests.
workflow-builder — the 8 workflows and prompts, with pydantic schemas.
frontend-builder — dashboard screens wired to the API.
verifier — runs offline test, network check, reply-accuracy eval; writes test_evidence/.
doc-writer — deliverable docs in docs/, licence table verified against real LICENSE files/model cards.

Definition of done (any task)

Code + test + make verify green + checkbox ticked in docs/TASKS.md + no new cloud references.
