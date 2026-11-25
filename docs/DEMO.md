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
RESULT: Reported live configuration: qwen3:4b, temperature 0, seed 42,
repeat_penalty 1.0, retry temperature 0.2, Windows laptop, about 18 tokens/s.
User-supplied local checks: Ollama 0.40.17; `qwen3:4b` ID 359d7dd4bcda,
2.5 GB; model licence Apache License 2.0 (January 2004).
Hardware: 15.7 GB RAM, 12 CPUs, 4.0 GB NVIDIA VRAM, standard-laptop tier,
recommended `qwen3:4b`, num_ctx 4096. `/api/status`: `ai_mode=local-only`,
Ollama available at `http://127.0.0.1:11434`, queue empty. These are
user-supplied command/API facts, not offline-acceptance script evidence.
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

Leave the API running. The embedded dashboard is at `http://127.0.0.1:8000/`.
All AI inference is routed to local Ollama at `127.0.0.1:11434`; this
application has no cloud fallback. The API has no user authentication; keep it
bound to loopback and do not expose it to a LAN.

```text
RESULT: Reply-import count and API startup output: not run.
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
RESULT: RelayCue profile and ICP succeeded. FieldNest ICP succeeded on the final
run (HTTP 200); an earlier run failed grounding after the model invented a
trigger event and disqualifier, and the failure was stored with its reason.
Product IDs, prospect import counts, and queued-retry counts: not run.
```

## 4. Run the product pipeline and inspect its saved progress

For the one-click workflow (which regenerates profile and ICP, processes every
currently imported prospect, and refreshes ranking), submit the product run and
use the returned ID to poll progress:

```bash
PIPELINE_ID="$(curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/pipeline" \
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
no LLM call is made. The fixed workflow allows `1` or `2` evidence spans of `4`–`15`
words each; each must be a substring of both verified signal evidence and the
prospect's current stored page text after case and whitespace normalization,
then appear enclosed in double quotes in the body. Problem statements use the
stored business profile and ICP plus this
prospect's latest successful verified-signal run. Their one- or two-sentence
statement must contain each of `1` or `2` verbatim `4`–`15`-word spans, and each
span must also occur in the verified signal evidence, after case/whitespace
normalization only. Without verified evidence, the result is `skipped` with
`no verified evidence` and no model call is made. Ranking reports an explicit
missing-input status when no signal run exists.

The model scores below are historical operator-reported results from earlier
prompts. They predate the Problem 7 confidence field and do not verify the
current schema or retry behavior; no new live or held-out run is claimed.

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
RESULT: Problem-statement POST/GET run on the target database, Ollama outage and
retry demonstration, dashboard browser click-through, and dashboard screenshot
(`docs/images/dashboard.png`): not run. The new offline-acceptance step is also
not run; no target-machine result, IDs, statuses, or counts have been supplied.
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
RESULT: Current workspace verification — `make verify` passed with 234 passed
and 2 skipped; the two local skips are PowerShell parser checks because
PowerShell is not installed here. Corpus validation and the no-cloud guard
passed. `npm run build` and `git diff --check` passed after the final edits.
These are automated/source checks, not a real Ollama or internet-off run.
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
are ignored by Git.

### Prepare the local demo data

On the target Windows laptop, start Ollama with the intended local model already
pulled, configure the API to use the local demo database, and start the API as
shown above. Ensure the DB has RelayCue and FieldNest products with their local
company-info paths, imported `SAMPLE_relaycue.csv` and `SAMPLE_fieldnest.csv`
prospects with local page paths, and the imported sample reply `R001`. No web
page is fetched by these scripts. IDs are resolved from the local API; pass an
explicit `-ProfileProductId`, `-FirstIcpProductId`, or `-SecondIcpProductId`
only when you need to select a different record.

### Run acceptance with Ollama available

From PowerShell in the repository root, with the API and Ollama running:

```powershell
.\scripts\offline_acceptance.ps1
```

The script checks API/hardware/status fields and the dashboard route at `/`,
resolves product IDs, then runs these workflows in order: business profile,
product ICP, research by reading saved prospect-page text, signals, problem
statement, deterministic scoring/ranking, unsent draft, and reply classification.
It runs the full resumable product pipeline as an extra final step, then checks
the reported Ollama host and established API-process peers. Standalone signals
are run for up to three stored-page RelayCue prospects. Problem-statement
evidence reports at most three prospect IDs, workflow statuses, and counts only;
it omits statement and source text. The pipeline summary records only step
counts/statuses, not child results or model output. The script prints `[PASS]`
or `[FAIL]` per step and writes timestamped `acceptance-*.log` and
`acceptance-*.json` files. Use `-SignalLimit` to change the standalone signal
sample, `-WaitSeconds` for individual workflows, and `-PipelineWaitSeconds` for
the full pipeline (default 900 seconds).

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

### Offline acceptance results

No files were present under `test_evidence/offline/` when this update was made.
The user supplied Ollama, model, hardware, status, and package facts below; these
are recorded as reported values, not as acceptance-script evidence. Internet-off
and Ollama-down outcomes remain `not run` until their evidence files exist.

| Check | Status | Evidence / result |
|---|---|---|
| `make verify` for the current workspace | passed — 234 passed, 2 skipped; corpus validation and no-cloud scan passed. | The two skips are PowerShell parser checks because PowerShell is unavailable here. Mocked/source checks, not live-model proof. |
| `npm run build` | passed. | React production bundle built successfully. |
| `git diff --check` | passed after the documentation edits. | No whitespace errors reported. |
| PowerShell script execution | not run — no PowerShell result is present in `test_evidence/offline/`. | Script syntax and real Windows networking behavior remain to be verified on the target laptop. |
| Ollama version, installed model list, and local status | reported by user — Ollama `0.40.17`; `qwen3:4b`, ID `359d7dd4bcda`, `2.5 GB`; `/api/status` local-only, available at loopback, queue empty. | User-supplied facts; not a timestamped acceptance-script result. |
| Hardware recommendation | reported by user — 15.7 GB RAM, 12 CPUs, 4.0 GB NVIDIA VRAM; standard-laptop, `qwen3:4b`, num_ctx 4096. | User-supplied `/api/hardware` output; not a timestamped acceptance-script result. |
| Qwen3 licence metadata | reported by user — Apache License 2.0, January 2004. | From the supplied `ollama show qwen3:4b --license` output; see `docs/LICENSES.md`. |
| `sentence-transformers` package metadata | reported by user — version `3.4.1`, Apache 2.0. | From the supplied `pip show sentence-transformers` output; see `docs/LICENSES.md`. |
| Offline acceptance against the local database/API | not run — no files were present in `test_evidence/offline/`. | No timestamped acceptance result exists yet. |
| Problem-statement target-machine acceptance step | not run. | The script is limited to at most three prospect IDs, statuses, and counts; it does not write statements or evidence text. |
| Ollama-down / recovery acceptance | not run until evidence files exist. | Do not treat mocked queue tests or the supplied status snapshot as a live outage test. |
| User's internet-off test | not run until evidence files exist. | Keep its result separate from these local-only scripts. |

### Unresolved limitations

The acceptance scripts have not been executed in PowerShell here. Runtime
behavior on the target Windows build, the `Get-NetTCPConnection` permission
requirements, the locally imported sample data, and live Ollama queue recovery
remain user verification items. Hardware GPU detection currently reports
NVIDIA VRAM via `nvidia-smi` only. The reported Ollama and Qwen3 values do not
verify Ollama's distribution licence or the embedding model's model-card
metadata; licence/version metadata for embedding transitive packages also
remain unavailable. See `docs/LICENSES.md`. Static source scans and mocks are
not a substitute for the internet-off test, which remains `not run` until its
evidence file exists.
