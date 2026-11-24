# Harvey Local AI Sales Agent

A local-first, multi-product sales-prospect research and drafting service. The
FastAPI backend uses SQLite for storage, Ollama at `127.0.0.1:11434` for local
LLM inference, and sentence-transformers for local embeddings. There is no
cloud inference, external enrichment API, email delivery, or paid-token
service.

> Upstream attribution: Harvey/Sellbird was created by Ethan Rogers and the
> Sellbird contributors, AGPL-3.0-only (earlier releases MIT). See `NOTICE` and
> `LICENSE`. This fork replaces the subscription-CLI architecture with
> local-only inference.

## Current capabilities

- Product-scoped profile and ICP generation from local product information.
- Product-scoped CSV prospect import and explicit local page-text storage.
- Buying-signal extraction with source-grounded evidence and persisted runs.
- Deterministic product-specific prospect rankings, including missing-input
  reporting and component explanations.
- Drafted outreach based only on a stored product profile and verified
  prospect signals. Drafts are persisted but **never sent**; when no verified
  evidence exists the workflow skips inference and records `no verified evidence`.
- Text-only sample-reply classification using eight validated labels, plus a
  separate offline evaluator. Ground-truth reply labels are isolated in
  `data/eval/reply_labels.csv`; they are never imported into the runtime database
  or included in model prompts.
- Persistent task queue for local Ollama outages; deterministic ranking remains
  available without an LLM call.

All model calls pass through `app/llm_client.py`, which is fixed to the local
Ollama endpoint. Structured responses are validated, retried at most twice,
and logged. Read `docs/WORKFLOWS.md` for contracts and `docs/KNOWN_LIMITATIONS.md`
for heuristic and model-evaluation caveats.

## Quickstart

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ollama serve                         # separate terminal
ollama pull qwen3:4b                 # one-time model download
DEFAULT_MODEL=qwen3:4b uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The service stores its SQLite database at `data/harvey.db` by default. Override
`DB_PATH` if needed. Ollama and downloaded local models must be installed before
running AI workflows; tests use mocked Ollama responses and do not need a live
model.

## Useful commands

```bash
make verify
python scripts/import_replies.py --db-path data/harvey.db
python scripts/eval_replies.py --model qwen3:4b                  # 36 development replies
python scripts/eval_replies.py --freeze-prompt                  # freeze reply prompt, no inference
python scripts/eval_replies.py --model qwen3:4b --held-out       # gated; requires matching freeze
```

`make verify` checks the local-only boundary, corpus metadata, and test suite;
it does not run Ollama or either held-out evaluator. The reply evaluator writes
redacted JSON reports beneath `test_evidence/real_run/`. It reports aggregate
metrics and misclassified IDs only, never reply text or rationale. See
`docs/DEMO.md` for ordered local demo commands and explicit placeholders for
results that still require a live local run.

## API highlights

- `POST /api/products` and `POST /api/products/{id}/prospects/import`
- `POST /api/products/{id}/profile` and `POST /api/products/{id}/icp`
- `GET /api/products/{id}/ranking`
- `POST` / `GET /api/products/{id}/prospects/{prospect_id}/draft`
- `POST` / `GET /api/replies/{reply_id}/classification`

The draft endpoint creates an unsent draft only. Email transmission is out of
scope.

## Licence

AGPL-3.0-only. See `LICENSE`, `NOTICE`, and `docs/MODELS_AND_LICENCES.md`.
