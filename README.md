# Harvey Local AI Sales Agent

A local-first, multi-product sales-prospect research and drafting service. The
FastAPI backend uses SQLite for storage, Ollama at `127.0.0.1:11434` for local
LLM inference, and sentence-transformers for local embeddings. There is no
cloud inference, external enrichment API, email delivery, or paid-token
service. No paid APIs are called or required; paid API cost is **$0**. Local
hardware, electricity, and one-time model-download bandwidth are user-provided
resources and are not priced here.

## Run locally and verify offline behavior

Inference goes only through `app/llm_client.py` to Ollama at
`http://127.0.0.1:11434`; there is no cloud API, API key, or cloud fallback.
Start the app with Python 3.11+, the local Ollama service, and a model already
pulled. The bundled UI is served by FastAPI; use `/operations` for the workflow
console.

1. Create and activate a virtual environment: `python -m venv .venv`.
2. Install the project and test tools: `pip install -e '.[dev]'`.
3. Run `python scripts/verify_no_cloud.py` and `pytest -q` for source and
   automated checks.
4. Start Ollama and pull the intended tag, for example `ollama pull qwen3:4b`;
   cache `sentence-transformers/all-MiniLM-L6-v2` while online before an
   internet-disconnected run.
5. Set `DEFAULT_MODEL` (and `OFFLINE_STRICT=1` after caching, if desired), then
   start the API bound to loopback:
   `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
6. Open `http://127.0.0.1:8000/operations`. For offline acceptance, disconnect
   Wi-Fi only after model caching, then run
   `scripts/offline_acceptance.ps1`; run `scripts/ollama_down_check.ps1`
   separately to test outage/recovery. Follow [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md)
   and preserve the actual log/JSON results. The `example.com` probe is not a
   complete network-isolation proof.

Failure handling is local: Ollama outages queue AI work for local replay, and
missing model tags report a local `ollama pull` instruction. Deterministic
ranking remains available without inference. `make verify` and `pytest -q` use
mocked Ollama responses and fake embeddings; passing tests are **not** proof of
live Ollama behavior, Windows acceptance, or network isolation.

> Upstream attribution: Harvey/Sellbird was created by Ethan Rogers and the
> Sellbird contributors. Upstream is AGPL-3.0-only from version 0.4.0 onward,
> and this fork keeps that licence; releases through 0.3.x have a separate MIT
> notice. See `NOTICE` and `LICENSE`. This fork replaces the subscription-CLI
> architecture with local-only inference.

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
- Drafted outreach using the stored product profile as context and verified
  signal quotes as the only evidence source. Every cited phrase is a literal,
  contiguous 4–15-word copy preserving case, punctuation, and spacing. Drafts
  are persisted but **never sent**; no-evidence cases skip inference.
- Evidence-grounded prospect problem statements use the profile and ICP only as
  context, never as quote sources, and accept evidence only from a separate
  `ALLOWED EVIDENCE` block of verified signal quotes. Results, source IDs,
  evidence spans, model settings, queue state, and failures are persisted.
- Text-only sample-reply classification using eight validated labels, plus a
  separate offline evaluator. Ground-truth reply labels are isolated in
  `data/eval/reply_labels.csv`; they are never imported into the runtime database
  or included in model prompts.
- Persistent task queue for local Ollama outages; deterministic ranking remains
  available without an LLM call.

All model calls pass through `app/llm_client.py`, which is fixed to the local
Ollama endpoint. JSON workflows disable model thinking (`think=false`), send the
Pydantic JSON schema to Ollama's structured `format` option, and use a 300-second
default timeout (`OLLAMA_TIMEOUT_SECONDS` can override it). Every structured
response is schema-validated; invalid output gets one stricter retry, then
fails with a stored reason. Read
`docs/WORKFLOWS.md` for contracts, `docs/HARDWARE.md` for recommendations,
`docs/FAILURE_HANDLING.md` for outage recovery,
`docs/NETWORK_AUDIT.md` for the outbound-client inventory,
`docs/COST_AND_DEPENDENCIES.md` for service costs and network needs,
`docs/MODELS_AND_LICENCES.md` for package/model licence status and outstanding
`VERIFY` items, and `docs/KNOWN_LIMITATIONS.md` for heuristic and
model-evaluation caveats.

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

### Windows PowerShell setup

Install Git, Python 3.11+, GNU Make, and Ollama first. From the repository root,
run these commands in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
make verify
ollama pull qwen3:4b
$env:DEFAULT_MODEL = "qwen3:4b"
$env:DB_PATH = "$PWD\data\harvey.db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If Ollama is not already running as a desktop service, start `ollama serve` in
a separate PowerShell window. `make verify` requires GNU Make on `PATH`; if it
is unavailable in PowerShell, run the check in Git Bash or WSL with the
repository's virtual environment active. Tests use mocked Ollama responses and
fake embeddings; `make verify` does not make a real Ollama request. It is an
automated check, not Windows, network-isolation, or live-model acceptance.

If PowerShell blocks activation, use a process-scoped execution-policy change
or invoke `.venv\Scripts\python.exe` directly; do not change the machine-wide
policy just for this project. Set `$env:OFFLINE_STRICT = "1"` before starting the
API if model files are already cached and you want Hub telemetry and
implicit-token use disabled. The embedding loader always sets Hugging Face and
Transformers offline flags. Set environment variables in the current shell;
the API and tests do not automatically read a `.env` file.

Keep the API bound to `127.0.0.1`; do not expose this unauthenticated service to
a LAN. The PowerShell acceptance scripts require the API, sample database, and
local Ollama runtime:

```powershell
.\scripts\offline_acceptance.ps1
.\scripts\ollama_down_check.ps1
```

`offline_acceptance.ps1` checks eight workflows in order and writes timestamped
logs and JSON beneath `test_evidence/offline/`. It makes one explicit
non-AI request to `https://example.com` as a connectivity indicator, so it is
not proof of a fully internet-disconnected run. `ollama_down_check.ps1`
interactively guides an Ollama stop/restart and writes evidence beneath
`test_evidence/ollama_outage/`. These scripts perform live local acceptance
only when an operator runs them; their source tests do not count as a real
Ollama result. The owner reports a Wi-Fi-disconnected run in which all eight
workflows worked, but the script invocation and matching offline log/JSON are
not present in this checkout. PowerShell script execution, network evidence,
and Ollama outage/recovery remain **PENDING**. Exact Windows cache, Wi-Fi-off,
eight-workflow, port-check, and outage/recovery instructions are in
[`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md); see
[`docs/PROJECT_STATUS_REPORT.md`](docs/PROJECT_STATUS_REPORT.md) for the owner-
reported results and current evidence inventory.

The API has no user authentication and is intended for one local operator:
bind it to `127.0.0.1` (as above), not `0.0.0.0` or a LAN address. Mutating
browser requests with a cross-origin `Origin` or `Sec-Fetch-Site: cross-site`
header are rejected. Product company-info paths are confined to
`data/company_info/`; CSV and prospect-page request bodies are size-limited.

The full product pipeline is available through
`POST /api/products/{id}/pipeline`. It queues profile and ICP generation,
processes up to three imported prospects' local pages in stable prospect-ID
order for signals, grounded problem statements and unsent drafts, then runs
product ranking. Three prospects produce 12 saved steps. Set the optional
positive-integer `prospect_limit` query parameter for a different per-run
snapshot, for example `POST /api/products/{id}/pipeline?prospect_limit=5`.
Poll saved progress with `GET /api/pipeline-runs/{run_id}` or read the latest
run with `GET /api/products/{id}/pipeline`. The API and the workflow console at
`/operations` both expose the full pipeline, prospect-limit input, and saved
step-by-step progress. The main React workspace at `/` is the dashboard; use
`/operations` to run and show the full pipeline during the demo. Import
prospects and store their local page text before starting. If Ollama is
unavailable, the run stays queued and resumes through the local worker when
available. A terminal profile or ICP failure skips all remaining steps with a
reason. Individual workflow endpoints remain available too.

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
`docs/DEMO.md` for ordered local demo commands, historical evaluation results,
and separately labeled owner-reported target results. The offline acceptance
procedure is in `docs/DEMO.md#offline-acceptance-test`; unprovided script output,
run IDs, and evidence paths remain marked `not run` or `not supplied` rather
than inferred from the owner's workflow report.

## Historical reported live-run snapshot

The figures below were reported for earlier prompts and are not evidence for
Problem 7's confidence-field schema, stricter retry behavior, or current
Windows/offline acceptance. The owner reports later local workflow runs; no new
model-quality metrics or held-out evaluation are claimed here. See
`docs/PROJECT_STATUS_REPORT.md` for those owner-reported facts and evidence
limits.

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
  All had `sent=false`; FieldNest drafts were not run. Those historical runs
  checked one or two `4`–`15`-word spans after case/whitespace normalization.
  The current validator instead requires a literal contiguous copy preserving
  capitalization, punctuation, and spacing in both the signal quote and body.
  The historical counts are not evidence of performance under this stricter
  check or a new real-Ollama run.
  In the successful example for prospect `22`, a four-word verified span was
  quoted in the body (`sent=false`).

No held-out reply or page text is included here.

## API highlights

- `POST /api/products` and `POST /api/products/{id}/prospects/import`
- `POST /api/products/{id}/profile` and `POST /api/products/{id}/icp`
- `GET /api/products/{id}/ranking`
- `POST` / `GET /api/products/{id}/prospects/{prospect_id}/draft`
- `POST` / `GET /api/products/{id}/prospects/{prospect_id}/problem-statement`
- `POST /api/replies/import-sample` imports text-only `data/sample/replies.csv`
  into SQLite; repeated imports update records by reply ID.
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

AGPL-3.0-only. See `LICENSE`, `NOTICE`, `docs/LICENSES.md`, and
`docs/MODELS_AND_LICENCES.md` for model/dependency status; unresolved items are
marked `VERIFY`.
