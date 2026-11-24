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
Ollama version, model-list output, and local service status: not run.
```

## 2. Create an isolated demo database and start the API

In terminal 2, from the repository root:

```bash
. .venv/bin/activate
export DB_PATH="$PWD/data/harvey-demo.db"
export DEFAULT_MODEL=qwen3:4b
python scripts/import_replies.py --db-path "$DB_PATH"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Leave the API running. The embedded dashboard is at `http://127.0.0.1:8000/`.
All AI inference is routed to local Ollama at `127.0.0.1:11434`; this
application has no cloud fallback.

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

## 4. Inspect ranking, signals, and an unsent draft

```bash
PROSPECT_ID="$(curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects" \
  | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
curl -fsS -X POST "http://127.0.0.1:8000/api/prospects/${PROSPECT_ID}/signals"
curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/ranking"
curl -fsS -X POST "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/${PROSPECT_ID}/draft"
curl -fsS "http://127.0.0.1:8000/api/products/${PRODUCT_ID}/prospects/${PROSPECT_ID}/draft"
```

Drafts are persisted locally with `sent=false` and are never sent. If there are
no valid signals, the draft status is `skipped` with reason `no verified evidence`;
no LLM call is made. The fixed workflow allows `1` or `2` evidence spans of `4`–`15`
words each; each must be a substring of verified signal evidence and the body after
case and whitespace normalization, with each span enclosed in double quotes in
the body. Ranking reports an explicit missing-input status when no signal run
exists.

```text
RESULT: Signals development (37 prospects; signal prompt hash prefix 73fa8d34...):
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
RESULT: Historical release-pass verification — make verify passed (156 tests);
git diff --check passed. Current Phase 2 verification: Filled after offline acceptance run.
```

## Offline acceptance test

These PowerShell scripts use only the local Harvey API over a loopback HTTP
connection. They do not call `pip`, `git`, or an external network service, and
they do not include response text, page text, reply text, rationale, or model
output in their evidence files. Evidence contains timestamps, statuses, counts,
model/settings/hash metadata, error classes, and record IDs only. Files are
written to `test_evidence/offline/` and ignored by Git.

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
resolves product IDs, runs profile and ICP workflows, extracts signals for up to
three stored-page RelayCue
prospects, checks deterministic rankings for both products, creates an unsent
draft, classifies `R001`, and checks the reported Ollama host and established
API-process peers. It prints `[PASS]` or `[FAIL]` per step and writes a
second-resolution timestamped `acceptance-*.json` evidence file. You can
increase the signal sample with `-SignalLimit` or adjust the workflow wait with
`-WaitSeconds`.

### Check outage, deterministic ranking, and retry

With the Harvey API left running, stop Ollama before starting this script. It
will prompt you to confirm the outage and later prompt you to start Ollama
again. It tests an AI signal request, persisted queued status/error and IDs,
ranking during the outage, queue counts, a worker wake request, and completion
of the same queued signal run after recovery:

```powershell
.\scripts\ollama_down_check.ps1
```

If Ollama was already stopped, use `-OllamaAlreadyStopped`. It writes a
second-resolution timestamped `ollama-down-*.json` file under the same evidence
directory. The script's maximum recovery wait is configurable with
`-WaitSeconds`.

### Offline acceptance results

| Check | Status | Evidence / result |
|---|---|---|
| `make verify` for the current implementation | passed — 165 tests; corpus validation and no-cloud scan passed. | Mocked/source checks, not live-model proof. |
| `git diff --check` | passed. | No whitespace errors reported. |
| PowerShell script execution | not run — `pwsh`/`powershell` unavailable in the sandbox. Filled after offline acceptance run. | Script syntax and real Windows networking behavior remain to be verified on the target laptop. |
| Ollama version, installed model list, and live status | not run — `ollama` executable unavailable (`ollama: command not found`). Filled after offline acceptance run. | No Ollama/Qwen3 version, installed-model, or live-inference claim is made. |
| Offline acceptance against the local database/API | not run — `data/harvey.db`, a live API, and Ollama were unavailable in the sandbox. Filled after offline acceptance run. | No timestamped acceptance result exists yet. |
| Ollama-down / recovery acceptance | not run — requires the user's running API and a manual stop/start of local Ollama. Filled after offline acceptance run. | Do not treat mocked queue tests as a live outage test. |
| User's internet-off test | not run by instruction. | Run manually on the target machine; keep its result separate from these local-only scripts. |

### Unresolved limitations

The acceptance scripts have not been executed in PowerShell here. Runtime
behavior on the target Windows build, the `Get-NetTCPConnection` permission
requirements, the locally imported sample data, and live Ollama queue recovery
remain user verification items. Hardware GPU detection currently reports
NVIDIA VRAM via `nvidia-smi` only. Exact Ollama/model-card metadata and licence
metadata for embedding/transitive packages remain unavailable; see
`docs/LICENSES.md`. Static source scans and mocks are not a substitute for the
manual internet-off test, which remains unrun.
