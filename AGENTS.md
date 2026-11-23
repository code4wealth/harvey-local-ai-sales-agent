# Harvey Local — Agent Roles and Rules

Shared non-negotiable rules are in `CLAUDE.md`: all inference goes through `app/llm_client.py` to local Ollama at `127.0.0.1:11434`; no cloud or paid inference and no fallback; no secrets; no hard-coded generated intelligence; and no email sending, paid research, or trainer default values.

## Runtime workflow agents

| Agent | File | Input | Output | Model use |
|---|---|---|---|---|
| Business profiler | `app/workflows/profile.py` | Product company documents | Summary, value proposition, features, solved pain points, differentiators | Yes |
| ICP generator | `app/workflows/icp.py` | Product profile | Industries, company-size range, buyer titles, pain points, triggers, disqualifiers | Yes |
| Prospect researcher | `app/workflows/research.py` | Locally stored prospect page text | Summary, activities, size hint, technology, recent news, similarity | Yes; embeddings are a separate local component |
| Signal classifier | `app/workflows/signals.py` | Source text and product ICP | Typed signals with evidence and confidence | Yes, then code verifies evidence |
| Problem writer | `app/workflows/problem.py` | Profile, research, verified signals | Grounded two- or three-sentence problem statement | Yes |
| Scorer | `app/scoring.py` | Similarity, signal score, size/title fit | Score from 0–100 with deterministic breakdown | No |
| Email writer | `app/workflows/email.py` | Profile, research, signals, problem, contact | Subject and body, fewer than 120 words, one CTA | Yes; generation only, never send |
| Reply classifier | `app/workflows/reply.py` | Reply text | Label, confidence, next action | Yes |
| Pipeline orchestrator | `app/pipeline.py` | Product ID | Per-step statuses and resumable workflow | Dispatch only |

Each model workflow builds a short prompt, calls `app/llm_client.py`, validates JSON with a dedicated Pydantic schema, persists results, and returns explicit errors. No workflow may call a model, provider CLI, or network directly. The research package may fetch public pages, but must not import the inference client.

## Development roles

- **Architect:** read-only structure and scope review.
- **Local-inference builder:** client, hardware, database, queue, and local-only tests.
- **Workflow builder:** prompts, schemas, evidence validation, and deterministic scoring.
- **Frontend builder:** dashboard components wired to the local API; all sample content visibly labelled.
- **Verifier:** runs the no-cloud guard, tests, offline checks, and records evidence without hiding failures.
- **Documentation writer:** maintains architecture, workflow, license, hardware, offline, failure, and known-limitations docs using verified facts.

## Definition of done

Code and tests are included, `make verify` passes after the legacy removal step, completed items are ticked in `docs/TASKS.md`, and no inference path bypasses the local client. Never add a dependency without approval and a license review.
