# Harvey Local AI Sales Agent

A local-first, multi-product sales-prospect research and drafting service. The
FastAPI backend uses SQLite for storage, Ollama at `127.0.0.1:11434` for local
LLM inference, and sentence-transformers for local embeddings. There is no
cloud inference, external enrichment API, email delivery, or paid-token
service. No paid APIs are called or required; paid API cost is **$0**. Local
hardware, electricity, and one-time model-download bandwidth are user-provided
resources and are not priced here.

> Upstream attribution: Harvey/Sellbird was created by Ethan Rogers and the
> Sellbird contributors, AGPL-3.0-only (earlier releases MIT). See `NOTICE` and
> `LICENSE`. This fork replaces the subscription-CLI architecture with
> local-only inference.

## Current capabilities

- A locally served React + Tailwind sales-intelligence dashboard at `/`, with
  the existing product and prospect workflows retained at `/operations`.
- Product-scoped profile and ICP generation from local product information.
- Product-scoped CSV prospect import and explicit local page-text storage.
- Optional **online-only** public-page collection via `scripts/fetch_public_pages.py`.
  It reads explicitly supplied URLs from CSV, observes `robots.txt`, and writes
  extracted text under `data/prospect_pages/`; it is separate from the API and
  local-inference path and is never run automatically.
- Buying-signal extraction with source-grounded evidence and persisted runs.
- Deterministic product-specific prospect rankings, including missing-input
  reporting and component explanations.
- Drafted outreach based only on a stored product profile and verified
  prospect signals. Drafts are persisted but **never sent**; when no verified
  evidence exists the workflow skips inference and records `no verified evidence`.
- Evidence-grounded prospect problem statements using the product's stored
  profile and ICP plus the prospect's latest successful verified-signal run.
  Results, source IDs, evidence spans, model settings, queue state, and failures
  are persisted; no-evidence cases skip inference.
- Text-only sample-reply classification using eight validated labels, plus a
  separate offline evaluator. Ground-truth reply labels are isolated in
  `data/eval/reply_labels.csv`; they are never imported into the runtime database
  or included in model prompts.
- Persistent task queue for local Ollama outages; deterministic ranking remains
  available without an LLM call.

All model calls pass through `app/llm_client.py`, which is fixed to the local
Ollama endpoint. Every structured response is schema-validated; invalid output
gets one stricter retry, then fails with a stored reason. Read
`docs/WORKFLOWS.md` for contracts, `docs/HARDWARE.md` for recommendations,
`docs/FAILURE_HANDLING.md` for outage recovery,
`docs/NETWORK_AUDIT.md` for the outbound-client inventory,
`docs/COST_AND_DEPENDENCIES.md` for service costs and network needs,
`docs/LICENSES.md` for the licence/version inventory and outstanding `VERIFY`
items, and
`docs/KNOWN_LIMITATIONS.md` for heuristic and model-evaluation caveats.

## Quickstart

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ollama serve                         # separate terminal
ollama pull qwen3:4b                 # one-time model download
DEFAULT_MODEL=qwen3:4b uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The service stores its SQLite database at `data/harvey.db` by default. Override
`DB_PATH` if needed. Ollama and downloaded local models must be installed before
running AI workflows; tests use mocked Ollama responses and do not need a live
model.

### Optional online page research

The FastAPI application uses only page text already stored locally. If fresh
public-page text is needed, run the separate, opt-in online helper with a CSV
containing a `url` column:

```bash
python scripts/fetch_public_pages.py urls.csv
```

The helper checks each site's `robots.txt`, applies request limits, and saves
text files under `data/prospect_pages/`. Review the fetched text and use its
printed relative path in a prospect CSV before running local workflows. This
helper requires internet access, does not discover URLs, and does not call or
import `app.llm_client`; do not use it for private or login-only pages. See
`docs/KNOWN_LIMITATIONS.md` for its scope and caveats.

### Dashboard frontend

The bundled React Router + Tailwind workspace is served from `/`; its nine
pages share one local-first application shell. The existing workflow console
remains available at `/operations`. The **Import Prospects** action opens a
product-scoped CSV mapping modal at `/prospects?import=true`. The production
bundle is checked in under `frontend/static`, so Node.js is not required to run
the Python quickstart.

To work on the UI, install the locked dependencies and run Vite in a separate
terminal while the API is running on port 8000:

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies only `/api`, `/operations`, and `/licenses` to FastAPI; Sellbird
workspace pages are handled by React Router. Rebuild the checked-in production
bundle after UI changes with `npm run build` from `frontend/`.

### Windows PowerShell setup (under 10 commands)

Install Python 3.11+, Ollama, and GNU Make first. From the repository root, run
these eight commands in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
make verify
ollama pull qwen3:4b
$env:DEFAULT_MODEL = "qwen3:4b"
$env:DB_PATH = "$PWD\data\harvey.db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If Ollama is not already running as a desktop service, start it with `ollama
serve` in a separate PowerShell window (ninth command). `make verify` requires
GNU Make on `PATH`; if it is not available in PowerShell, run that command in
Git Bash or WSL with the repository's Python environment active. The check suite
uses mocked Ollama responses and fake embeddings; it does not need a live model.

An earlier Windows run was reported as **224 passed, 1 skipped**, before the
optional public-page helper and its tests were added. The current workspace
measured **234 passed, 2 skipped** with `make verify`; both skips are PowerShell
parser checks because PowerShell is not installed here. This is not a current
Windows result: rerun `make verify` on the target laptop to establish its count.
Keep the API on
`127.0.0.1`; do not expose it to a LAN. Set `$env:OFFLINE_STRICT = "1"` before
starting the API to disable Hugging Face Hub telemetry and implicit-token use
during local embedding loads; model files must already be cached. The loader
always enforces Hugging Face and Transformers offline flags. The API and test
suite do not automatically read a `.env` file; set environment variables in the
current shell.

The API has no user authentication and is intended for one local operator:
bind it to `127.0.0.1` (as above), not `0.0.0.0` or a LAN address. Mutating
browser requests with a cross-origin `Origin` or `Sec-Fetch-Site: cross-site`
header are rejected. Product company-info paths are confined to
`data/company_info/`; CSV and prospect-page request bodies are size-limited.

From the dashboard, choose a product and use **Run full product workflow** to
queue profile and ICP generation, process up to three imported prospects' local
pages (stable prospect-ID order) for signals, grounded problem statements and
unsent drafts, then refresh product ranking. Three prospects produce 12 saved
steps; increase the per-run prospect limit in the dashboard for a longer demo.
The API accepts the same positive-integer option, for example
`POST /api/products/{id}/pipeline?prospect_limit=5`. The dashboard polls
persisted per-step progress; the other API equivalents are
`GET /api/pipeline-runs/{run_id}` and `GET /api/products/{id}/pipeline`. Import
prospects and store their local page text before starting. If Ollama is
unavailable, the run stays queued and resumes through the local worker when
available. A terminal profile or ICP failure skips all remaining steps with a
reason. Individual steps remain available too.

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
snapshot. The offline acceptance procedure is in
`docs/DEMO.md#offline-acceptance-test`; unavailable outputs are marked `not run`
and unreported outcomes are marked `not supplied`.

## Historical reported live-run snapshot

The figures below were reported for earlier prompts and are not evidence for
Problem 7's confidence-field schema, stricter retry behavior, or current
Windows/offline acceptance. No new live-model run is claimed here.

Configuration: `qwen3:4b`, temperature `0`, seed `42`, `repeat_penalty=1.0`,
retry temperature `0.2`, Windows laptop, about 18 tokens/s. All data is fictional
`SAMPLE` data. Unavailable run outputs remain marked `not run`; unreported
outcomes remain marked `not supplied`.

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
- Signals ran for all `41` prospect rows (`21` RelayCue, `20` FieldNest); saved
  rankings are under `test_evidence/real_run/`. Ranking returns an explicit
  missing-input status when no signal run exists. Reply classification of
  `R001` returned `interested` with confidence `0.95`.
- Drafts, first attempt (`9` prospects): `6` skipped with `no verified evidence`
  and `3` failed the verbatim-evidence check after the model paraphrased; none
  were sent.
- Drafts after the fix (`6384b4b`, `156` tests): across `21` RelayCue prospects,
  `7` succeeded (IDs `22`, `28`, `30`, `32`, `34`, `35`, `36`), `12` skipped
  with `no verified evidence`, and `2` failed (`25`, `37`) with stored reasons.
  All had `sent=false`; FieldNest drafts were not run. `evidence_used` contains
  `1` or `2` verbatim spans of `4`–`15` words; each must be a substring of verified
  signal evidence and the body after case and whitespace normalization, and appear
  in double quotes in the body.
  In the successful example for prospect `22`, a four-word verified span was
  quoted in the body (`sent=false`).

No held-out reply or page text is included here.

## API highlights

- `POST /api/products` and `POST /api/products/{id}/prospects/import`
- `POST /api/products/{id}/profile` and `POST /api/products/{id}/icp`
- `GET /api/products/{id}/ranking`
- `POST` / `GET /api/products/{id}/prospects/{prospect_id}/draft`
- `POST` / `GET /api/products/{id}/prospects/{prospect_id}/problem-statement`
- `POST` / `GET /api/replies/{reply_id}/classification`
- `GET /health` checks API/SQLite liveness without requiring Ollama
- `GET /api/hardware` and `GET /api/status`
- `POST /api/queue/retry` (wakes the local queue worker)

Generated workflow results include model settings, a SHA-256 of the rendered
prompt, and the checked-out source commit when available. `/api/status` reports
the latest inference trace; legacy rows and packaged builds may show hashes as
unknown.

The draft endpoint creates an unsent draft only. Email transmission is out of
scope.

## Licence

AGPL-3.0-only. See `LICENSE`, `NOTICE`, and `docs/LICENSES.md` (with model notes in `docs/MODELS_AND_LICENCES.md`).
