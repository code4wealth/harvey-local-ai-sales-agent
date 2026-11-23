# Harvey Local Multi-Product AI Sales Agent — Project Memory

## Project

This repository is the local-first Harvey multi-product sales-agent assignment. Read `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOWS.md`, and `docs/TASKS.md` before changing product behavior.

## The one rule

All AI inference goes through **one file**, `app/llm_client.py`, and only to the local Ollama server at `http://127.0.0.1:11434`.

- Do not add hosted inference, paid AI services, provider SDKs, account-backed model CLIs, or a cloud fallback.
- If Ollama is unavailable, surface `OllamaUnavailable`, queue AI work for retry, and keep deterministic features usable.
- Never present hard-coded output as generated intelligence. Generated profile, ICP, signal, problem, email, and reply results must come from the local model; scoring is deterministic code.
- Never commit secrets. The application needs no AI keys, and `.env.example` must not contain any.
- Internet access for optional public-web research is not AI. Keep it in `app/research/`, which must not import `app/llm_client.py`; the inference client must never import research code.
- Do not implement email sending, paid research/enrichment, CRM integrations, multi-user authentication, or trainer default values.

## Stack and dependencies

Python 3.11+, FastAPI, SQLite via the standard-library `sqlite3`, HTTPX, Pydantic v2, and local Ollama. `psutil` is the only newly approved dependency for the current foundation. Do not add `sentence-transformers` until Phase 2; first document its license and the licenses of all transitive dependencies and obtain approval. Keep dependency licenses documented and dependencies pinned or bounded consistently in `pyproject.toml` and `requirements.txt`.

## Target layout

```text
app/
  main.py                 FastAPI app and routes
  llm_client.py           only AI path; fixed local Ollama host
  hardware.py             RAM/CPU/GPU detection and model recommendation
  db.py                   SQLite schema and helpers
  queue_worker.py         retries queued AI tasks when Ollama returns
  embeddings.py           local embeddings (future; license approval required)
  scoring.py              deterministic hybrid scoring
  workflows/              profile, ICP, research, signals, problem, email, reply
  research/               public-web research only; no model calls

data/                     clearly labelled SAMPLE inputs; ignored local DB
frontend/                 local dashboard
scripts/                  verification, offline test, reply evaluation
tests/                    local HTTP mocks and deterministic unit tests
docs/                     requirements, architecture, workflows, acceptance, evidence
```

## Runtime rules and conventions

- Use type hints, small functions, and Pydantic models for model-generated JSON. Validate outputs and retry invalid JSON at most twice.
- For Qwen3 requests send `"think": false`; defensively strip `<think>...</think>` blocks from responses.
- Log every inference call in SQLite with task, model, fixed host, prompt/evaluation token counts when reported, latency, timestamp, and outcome.
- Every buying signal needs an evidence quote. Verify the quote against the source text after case/whitespace normalization; discard unverified signals.
- Numeric prospect scores are computed deterministically and remain available while Ollama is down. An optional text rationale may be skipped.
- Mark all mock/sample data `SAMPLE` in source files and the UI. Do not invent intelligence or trainer fallback defaults.
- Keep secrets in environment variables only; never commit `.env`.

## Commands

```sh
ollama serve
ollama pull qwen3:4b
uvicorn app.main:app --reload
pytest -q
python scripts/verify_no_cloud.py
make verify
python scripts/offline_test.py
```

Run `make verify` and the relevant tests after each implementation commit. Do not weaken the verifier to conceal a failure; fix the underlying reference or behavior. The developer reconnaissance file under `docs/dev/` is explicitly excluded from the literal reference scan.

## Working agreement

1. Follow `docs/TASKS.md` phase by phase; tick tasks only when complete.
2. After each requested commit, run `make verify` and tests, and report any failure honestly.
3. Ask before adding dependencies; the only current approval is `psutil` (BSD-3-Clause).
4. Prefer simple, deterministic behavior. Small local models need short prompts, JSON examples, validation, and bounded retries.
5. Stop at the approved scope. Do not add email sending, paid research, or trainer defaults.
