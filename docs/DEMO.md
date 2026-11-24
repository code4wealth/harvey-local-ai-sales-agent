# Local demo runbook

This runbook is for a real local Ollama demonstration. The commands are listed
in execution order but have **not** been run for the current workflow changes.
Do not present mocked tests as live-model evidence. Fill each `RESULT` line only
after the corresponding live command completes.

## 1. Install and start local Ollama

From the repository root (Python 3.11+ and Ollama must already be installed):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ollama pull qwen3:4b
```

In terminal 1, start Ollama if the desktop/service is not already running:

```bash
ollama serve
```

```text
RESULT: fill after live run — record Ollama version, model list, and local service status.
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
RESULT: fill after live run — record the actual reply-import count and API startup result.
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
RESULT: fill after live run — record product ID, prospect import counts, profile/ICP statuses, and any queued retries.
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

A draft is persisted locally and is never sent. If there are no valid signals,
the draft status is `skipped` with reason `no verified evidence`; no LLM call is
made. Ranking remains deterministic and reports missing components rather than
inventing inputs.

```text
RESULT: fill after live run — record signal-run status, ranking status/tier, and draft status. Do not claim email was sent.
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
rationale. **Do not run the held-out evaluator as part of this demo.** The
held-out split is reserved and requires a matching frozen reply-prompt hash.

```text
RESULT: fill after live run — record the actual development accuracy, per-label/per-difficulty metrics, report path, and duration.
```

## 6. Verify implementation without running a live or held-out evaluation

```bash
make verify
git diff --check
```

These checks use tests and mocked Ollama responses; they do not count as a live
model demonstration. No held-out evaluation is authorized by this runbook.

```text
RESULT: fill after live run — record command exit codes and test count.
```
