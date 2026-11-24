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

- Small, static, no-build/no-external-network dashboard served at `/`.
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
`docs/DEMO.md` for ordered local demo commands and the reported live-run
snapshot; unavailable run outputs are marked `not run`, and unreported outcomes
are marked `not supplied`.

## Reported live-run snapshot

Configuration: `qwen3:4b`, temperature `0`, seed `42`, `repeat_penalty=1.0`,
retry temperature `0.2`, Windows laptop, about 18 tokens/s. Unavailable run
outputs are marked `not run`; unreported outcomes are marked `not supplied`.

- Signals, development (37 prospects; signal prompt hash prefix `73fa8d34...`):
  expected-signal recall `14/16 (87.5%)`; `34/37` prospects passed; `1` false
  positive on an implied-signal page (`P010`); misses `P001` (quote glitch
  persisted after `2` quote retries) and `P022` (model returned nothing); `8`
  quote-verification retries in total.
- Signals, held-out (12 pages, one run): expected-signal recall `8/8 (100%)`;
  `9/12` pages passed (failed `P045`, `P047`, `P049`); false positives: no-signal/
  implied `1`, negated `1`, other-company `1`; stale-signal trap held; empty-list
  returns `0/12`; `4` quote drops, `2` negated drops.
- Replies, development before one prompt revision (36): `27/36 (75.0%)`;
  wrong_person `1/4`, other `1/4`, interested `3/5`.
- Replies, development after the revision (36): `32/36 (88.9%)`; ambiguous
  `9/10`, clear `23/26`; misclassified IDs `R025`, `R028`, `R039`, `R043`.
- Replies, held-out (24, one run; prompt frozen, hash prefix `a369052a...`):
  `18/24 (75.0%)`; per-label counts: interested `2/3`, meeting_request `2/3`,
  not_interested `2/3`, other `1/3`, out_of_office `3/3`, question `2/3`,
  unsubscribe `3/3`, wrong_person `3/3`; ambiguous `6/10 (60%)`, clear
  `12/14 (85.7%)`; misclassified IDs `R014`, `R018`, `R019`, `R048`, `R050`,
  `R060`.
- Profile and ICP: RelayCue profile and ICP succeeded. FieldNest ICP succeeded
  on the final run (HTTP 200); an earlier run failed grounding after the model
  invented a trigger event and disqualifier, and the failure was stored with
  its reason.
- Demo behavior: ranking returned an explicit missing-input status when no
  signal run exists; the draft was skipped with `no verified evidence` and was
  never sent; reply classification of `R001` returned `interested`.

No held-out reply or page text is included here.

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
