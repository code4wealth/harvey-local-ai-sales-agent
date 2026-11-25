# Local demo runbook

This runbook is for a real local Ollama demonstration. The commands are listed
in execution order; not every command output is present in the supplied run
record. Unavailable run outputs are marked `not run`, unreported outcomes are
marked `not supplied`, and held-out run counts are recorded separately. Do not
present mocked tests as live-model evidence or include held-out reply/page text.

## 1. Install and start local Ollama

From the repository root (Python 3.11+ and Ollama must already be installed):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

In terminal 1, start Ollama if the desktop/service is not already running:

```bash
ollama serve
```

In terminal 2, from the repository root, pull the model:

```bash
. .venv/bin/activate
ollama pull qwen3:4b
```

```text
RESULT: Earlier operator-reported configuration and checks (not confirmed for
the current owner-reported run): `qwen3:4b`, temperature 0, seed 42,
`repeat_penalty=1.0`, retry temperature 0.2, Windows laptop; Ollama 0.40.17,
reported digest `359d7dd4bcda`, 2.5 GB, and Apache License 2.0; 15.7 GB RAM,
12 CPUs, 4.0 GB NVIDIA VRAM, standard-laptop tier, `num_ctx=4096`. These values
are historical reports, not independently checked licences or current run
metadata. The current owner report confirms `qwen3:4b` local inference and an
approximate 66% GPU / 34% CPU split, but gives no current Ollama version or
digest. See the owner-reported run section below.
```

## 2. Create an isolated demo database and start the API

In terminal 2, from the repository root:

```bash
. .venv/bin/activate
export DB_PATH="$PWD/data/harvey-demo.db"
export DEFAULT_MODEL=qwen3:4b
python scripts/import_replies.py --db-path "$DB_PATH"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave the API running. The React workspace is at `http://127.0.0.1:8000/`;
the full-pipeline controls used in this demo are in the workflow console at
`http://127.0.0.1:8000/operations`. All AI inference is routed to local Ollama
at `127.0.0.1:11434`; this application has no cloud fallback. The API has no
user authentication; keep it bound to loopback and do not expose it to a LAN.

```text
RESULT: The owner reports 60 SAMPLE replies imported in the online FieldNest
run. API startup output and the exact run/import response were not supplied.
```

## 3. Create a product, import prospects, and run its profile and ICP

In terminal 3, from the repository root:

```bash
. .venv/bin/activate
PRODUCT_ID="$(curl -fsS -X POST http://127.0.0.1:8000/api/products \
  -H 'Content-Type: application/json' \
  -d '{"name":"RelayCue","description":"Fictional support handoff workspace","docs_path":"data/company_info/relaycue.md"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/import" \
  --data-binary @data/prospects/SAMPLE_relaycue.csv
curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/profile"
curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/icp"
```

If Ollama is unavailable, the POST response may be `202` with a queued run.
Check the corresponding `GET` endpoint after the worker retries. The commands
use only fictional SAMPLE product/prospect data.

```text
RESULT: Earlier operator-reported runs: RelayCue profile/ICP succeeded and a
final FieldNest ICP succeeded after an earlier grounding failure. Separately,
the owner reports profile and ICP completed in the online FieldNest run, with
20 prospects imported (the checked-in CSV has 20 data rows). Exact product IDs,
HTTP response, and queued-retry counts for the owner run were not supplied.
```

## 4. Run the product pipeline and inspect its saved progress

For the visual demo, open `http://127.0.0.1:8000/operations`, choose the
product, and use **Run full product workflow**. The console exposes the
prospect-limit field and **View latest progress** control; it shows the same
persisted run as the API. For repeatable command-line steps, the commands below
submit that API run (which regenerates profile and ICP, processes up to three
currently imported prospects in stable ID order, and refreshes ranking). Change
`prospect_limit` in the `/operations` console or API query string for a longer
run:

```bash
PIPELINE_ID="$(curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/pipeline?prospect_limit=3" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
curl -fsS "http://127.0.0.1:8000/api/pipeline-runs/${PIPELINE_ID}"
```

The run and its profile, ICP, per-prospect signal/problem/draft, and ranking
steps remain available after a browser reload. While Ollama is unavailable,
queued work resumes through the local worker after recovery. The commands below
remain useful when demonstrating individual steps instead of the full run.

```bash
PROSPECT_ID="$(curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects" \
  | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
curl -fsS -X POST "http://127.0.0.1:8000/api/prospects/${PROSPECT_ID}/signals"
curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/ranking"
curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/${PROSPECT_ID}/draft"
curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/${PROSPECT_ID}/draft"
curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/${PROSPECT_ID}/problem-statement"
curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/${PROSPECT_ID}/problem-statement"
```

Drafts are persisted locally with `sent=false` and are never sent. If there are
no valid signals, the draft status is `skipped` with reason `no verified evidence`;
no LLM call is made. The current draft workflow allows `1` or `2` exact,
contiguous `4`–`15`-word fragments copied verbatim from verified signal quotes;
capitalization, punctuation, and spacing must match the stored page text and
signal evidence exactly, and each fragment must be double-quoted in the body.
Problem statements use the stored business profile and ICP only as context plus
this prospect's latest successful verified-signal run. Profile and ICP text
must never be cited; only the signal quotes in `ALLOWED EVIDENCE` may be used.
Each one- or two-sentence statement must contain one or two exact, contiguous
`4`–`15`-word fragments copied from that block and present verbatim in the
statement. Without verified evidence, the result is `skipped` with `no verified
evidence` and no model call is made. Ranking reports an explicit missing-input
status when no signal run exists.

The model scores below are historical operator-reported results from earlier
prompts. They predate the Problem 7 confidence field and do not verify the
current schema or retry behavior. The owner reports a later local workflow run,
but no new model-quality metrics or held-out evaluation result are supplied.

```text
RESULT: Signals development (37 prospects; historical signal prompt hash prefix 73fa8d34...):
expected-signal recall 14/16 (87.5%); 34/37 prospects passed; 1 implied-signal
false positive (P010); misses P001 (quote glitch persisted after 2 quote retries)
and P022 (model returned nothing); 8 quote-verification retries in total.
Signals held-out (12 pages, one run): expected-signal recall 8/8 (100%);
9/12 pages passed (failed P045, P047, P049); trap false positives:
no-signal/implied 1, negated 1, other-company 1; stale-signal trap held;
empty-list returns 0/12; 4 quote drops, 2 negated drops. Signals ran for all 41
prospect rows (21 RelayCue, 20 FieldNest); rankings were saved to
test_evidence/real_run/. Ranking returned an explicit missing-input status when
no signal run exists.
Drafts, first attempt (9 prospects): 6 skipped with `no verified evidence` and
3 failed the verbatim-evidence check because the model paraphrased; none were
sent. After the fix (commit 6384b4b; 156 tests), 21 RelayCue prospects had 7
successful drafts (IDs 22, 28, 30, 32, 34, 35, 36), 12 skipped with `no verified
evidence`, and 2 failed (IDs 25, 37) with stored reasons; all had `sent=false`.
FieldNest drafts were not run. In the successful example for prospect 22, a
four-word verified span was quoted in the body; status succeeded, sent false.
```

```text
RESULT: The owner reports problem statement, draft, and ranking completed in
the online FieldNest run and all eight workflows completed with Wi-Fi
disconnected. Exact target POST/GET responses, run IDs, per-step statuses,
timestamps, and logs were not supplied; use the owner-reported results section
below rather than treating this as script evidence. The invocation of
`offline_acceptance.ps1` was not confirmed, and no offline log/JSON is present.
The static dashboard image `docs/images/dashboard.png` is not a target-run
screenshot. Ollama outage/recovery remains unresolved.
```

## 5. Classify one sample reply and run the development evaluator

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/replies/R001/classification
curl -fsS http://127.0.0.1:8000/api/replies/R001/classification
python scripts/eval_replies.py --model qwen3:4b
```

The evaluator defaults to the 36 development replies and stores a redacted
report under `test_evidence/real_run/`. Reports contain aggregate metrics,
confusion counts, and misclassified IDs only; they do not contain reply text or
rationale. **Do not rerun the held-out evaluator as part of this demo.** The
supplied run record says the 24-example held-out reply set was run once; the
held-out evaluator remains gated by a matching frozen reply-prompt hash.

```text
RESULT: Replies development before one prompt revision (36): 27/36 (75.0%);
wrong_person 1/4, other 1/4, interested 3/5. After the revision (36): 32/36
(88.9%); ambiguous 9/10, clear 23/26; misclassified IDs R025, R028, R039, R043.
Replies held-out (24, one run, prompt frozen, hash prefix a369052a...): 18/24
(75.0%); per-label counts: interested 2/3, meeting_request 2/3,
not_interested 2/3, other 1/3, out_of_office 3/3, question 2/3, unsubscribe
3/3, wrong_person 3/3; ambiguous 6/10 (60%), clear 12/14 (85.7%);
misclassified IDs R014, R018, R019, R048, R050, R060. Report path and
duration: not supplied. The live classification of R001 returned `interested`
with confidence `0.95`.
```

## 6. Verify implementation without rerunning live or held-out evaluations

```bash
make verify
git diff --check
```

These checks use tests and mocked Ollama responses; they do not count as a live
model demonstration and do not rerun either held-out evaluator.

```text
RESULT: Current workspace verification — `PATH="$PWD/.venv/bin:$PATH" make verify`
passed with 250 passed and 2 skipped; the two local skips are PowerShell parser
checks because PowerShell is not installed here. Corpus validation and the
no-cloud guard passed. The frontend production build and `git diff --check` also
passed. These are automated/source checks, not full live Ollama or internet-off
acceptance.
```

## Offline acceptance test

Both PowerShell scripts call the Harvey API only over loopback and do not call
`pip`, `git`, or any external AI service. The offline acceptance script makes
one explicit, non-AI HTTPS request to `example.com` as an internet-connectivity
indicator; if it receives an HTTP response, it marks the run as **not offline**.
That single probe is not a complete firewall or network-isolation proof. The
Ollama outage script contacts only the local Harvey API and Ollama endpoints.
Neither script includes response text, page text, reply text, rationale, or
model output in its evidence files. Evidence contains timestamps, statuses,
counts, model/settings/hash metadata, error classes, and record IDs only. The
main acceptance log is written to `test_evidence/offline/`; the separate outage
log is written to `test_evidence/ollama_outage/`. Those generated run folders
are ignored by Git. For exact Windows model-cache, `HF_HUB_OFFLINE=1`, Wi-Fi
adapter, `netstat`, `ollama ps`, and demo talk-track instructions, see
[`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

### Prepare the local demo data

On the target Windows laptop, start Ollama with the intended local model
already pulled, configure the API to use the local demo database, and start the
API as shown above. Ensure the database has a RelayCue product, imported sample
prospects with local page paths, and sample reply `R001`. If the reply is not in
the runtime table, import the text-only fixture locally with
`POST /api/replies/import-sample` or `python scripts/import_replies.py`; labels
remain in the separate evaluator data. No web page is fetched by these scripts.
The default profile and ICP product is RelayCue; pass `-ProfileProductId` or
`-IcpProductId` to select different records.

### Run acceptance with Ollama available

From PowerShell in the repository root, with the API and Ollama running:

```powershell
.\scripts\offline_acceptance.ps1
```

The script checks API/hardware/status fields and resolves product IDs, then
runs exactly these eight workflows in order: business profile, product ICP,
research by reading saved prospect-page text, signals, problem statement,
deterministic scoring/ranking, unsent draft, and reply classification. It then
checks runtime traceability and the API process's non-loopback connection
snapshot. The script selects the first RelayCue prospect with stored page text;
problem-statement evidence in the report is limited to status and counts, not
the statement or source text. The full resumable product pipeline is a separate
API workflow and is not a ninth acceptance-script entry. The script prints
`[PASS]` or `[FAIL]` per step and writes timestamped `acceptance-*.log` and
`acceptance-*.json` files. Use `-ProfileProductId`, `-IcpProductId`, and
`-ReplyId` to select records, or `-WaitSeconds` to adjust individual-workflow
polling (default 300 seconds).

### Check outage, deterministic ranking, and retry

With the Harvey API left running, start this script and follow its prompts to
stop Ollama before the task and restart it after the queued state is recorded.
It tests an AI signal request, confirms the queued status and IDs, checks
ranking during the outage, records queue counts, requests a worker wake, and
polls for completion of the same queued signal run after recovery:

```powershell
.\scripts\ollama_down_check.ps1
```

If Ollama was already stopped, use `-OllamaAlreadyStopped`. It writes
timestamped `ollama-down-*.log` and `ollama-down-*.json` files under
`test_evidence/ollama_outage/`. The recovery wait is configurable with
`-WaitSeconds`.

### Owner-reported target-laptop results and acceptance evidence

The owner confirms the reported Windows-run date as **2026-11-26**. This date
is later than the current workspace snapshot/system date (**2026-11-23 UTC**),
so the run remains a future-dated owner report, not an outcome independently
verified from a target-laptop capture in this checkout.

The owner reports live local `qwen3:4b` inference via Ollama, with `ollama ps`
showing about 66% GPU / 34% CPU on an RTX 3050 (15.7 GB RAM, 12 CPUs). The
online FieldNest run reportedly completed profile, ICP, signals, problem
statement, draft, and ranking; 20 prospects and 60 sample replies were
imported. The owner reports `R004` classified `not_interested`, matching the
ambiguous development label in `data/eval/reply_labels.csv`. Separately, the
owner reports all eight workflows worked with Wi-Fi disconnected and that the
offline run was screen-recorded. The exact script, `.log`/`.json`, ping result,
`netstat` capture, screenshot files, outage result, video link, and demo footer
commit were not supplied.

Files actually present under `test_evidence/` are `online/README.md` (template
only), `real_run/smoke_embeddings.txt`, and `real_run/smoke_ollama.txt` (earlier
smoke records). There are no files under `test_evidence/offline/` or
`test_evidence/ollama_outage/`, and no screenshot image is present under
`test_evidence/` in this checkout. Three static UI images under `docs/images/`
are not evidence from the owner-reported run. The owner's screen recording is
not present in these folders.

| Check | Status | Evidence / result |
|---|---|---|
| `make verify` for the current workspace | passed — 250 passed, 2 skipped; corpus validation and no-cloud scan passed. | The two skips are PowerShell parser checks because PowerShell is unavailable here. Mocked/source checks, not live-model proof. |
| `npm run build` | passed with Vite 6.4.6 after frontend changes. | Generated the checked-in production bundle; this is not browser or live-API acceptance. |
| `git diff --check` | passed after the current source and documentation edits. | No whitespace errors reported. |
| PowerShell script execution | **PENDING** — the owner reports an eight-workflow offline run, but did not confirm whether `offline_acceptance.ps1` ran. | No PowerShell log/JSON exists in this checkout; retain the owner report separately from script execution. |
| Current owner-reported local inference | **Owner-reported:** `qwen3:4b` via local Ollama; the latest Ollama version, exact installed digest, and status JSON were not supplied. | The tracked one-call smoke log is earlier evidence and is not asserted to match the Nov 26 owner run. |
| Target runtime placement | **Owner-reported:** RTX 3050, 15.7 GB RAM, 12 CPUs; `ollama ps` showed about 66% GPU / 34% CPU. | No runtime capture is present here; no embedding-device information was supplied. Earlier hardware-recommendation facts are not treated as this run's output. |
| CPU/GPU inference split | **Owner-reported** — about 66% GPU / 34% CPU on RTX 3050. | The value was not independently inspected; no `ollama ps` file is present in this checkout. |
| Embedding-device placement | **PENDING** — not supplied. | `ollama ps` does not establish the embedding device; capture the embedding runtime separately if required. |
| Qwen3 licence metadata | Earlier owner-reported Apache License 2.0; **still VERIFY** against the current exact tag/manifest. | The earlier `ollama show qwen3:4b --license` report is not an independent check of the current artifact or digest; see the official pages in `docs/MODELS_AND_LICENCES.md`. |
| `sentence-transformers` package metadata | reported by user — version `3.4.1`, Apache 2.0. | From the supplied `pip show sentence-transformers` output; see `docs/LICENSES.md`. |
| Wi-Fi-disconnected eight-workflow run | **Owner-reported complete** — all eight workflows worked; screen-recorded. | The script used and recording path were not supplied; no offline log/JSON is present in this checkout. |
| Problem-statement target-machine workflow | **Owner-reported complete** in the online FieldNest run and as part of the reported offline eight workflows. | No target output, run ID, or acceptance log was supplied; do not infer statement quality from completion status. |
| Ollama-down / recovery acceptance | **PENDING** — the owner did not resolve the `[DONE and recorded / NOT DONE]` choice. | No outage result or file is present; mocked queue tests are not live outage evidence. |
| Wi-Fi-disconnected test | **Owner-reported complete** for all eight workflows. | Whether ping failed and whether `netstat` on port 11434 was captured were left as unresolved choices; no network trace is present here. A successful Wi-Fi toggle is not comprehensive network-isolation proof. |
| Demo video / footer commit | **PENDING** — no URL or hash was supplied. | The offline screen recording is reported but not linked or present in this checkout; confirm the video matches the final commit. |
| Screenshot evidence | **PENDING** — no screenshot image exists under `test_evidence/` in this checkout. | `test_evidence/online/README.md` is a template, not a screenshot. |

### Unresolved limitations

The owner reports the Wi-Fi-disconnected eight-workflow run and a live local
inference run, but the PowerShell script execution, `.log`/`.json`, ping result,
`netstat` observation, and complete network trace were not supplied. Treat the
workflow outcome as owner-reported, not independently verified; it is not proof
that every outbound route was blocked. The owner-reported `ollama ps` split is
also not present as a capture, and no embedding-device or performance
measurement was supplied. Ollama-down/recovery remains **PENDING**. Target
Windows package resolution and all model/runtime licence items remain
**VERIFY** in `docs/MODELS_AND_LICENCES.md`; historical user reports do not
replace checking the exact installed artifacts and official pages. Static
source scans and mocked tests are not a substitute for these target checks.
