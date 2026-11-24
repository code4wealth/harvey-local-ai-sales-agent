# Local demo runbook

This runbook is for a real local Ollama demonstration. The commands are listed
in execution order; not every command output is present in the supplied run
record. Missing result values are marked `not run`, and supplied held-out run
counts are recorded separately. Do not present mocked tests as live-model
evidence or include held-out reply/page text.

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
RESULT: Reported live configuration: qwen3:4b, temperature 0, seed 42, repeat_penalty 1.0, Windows laptop, about 18 tokens/s. Ollama version, model-list output, and local service status: not run.
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
RESULT: Both products produced filled, different ICPs; company size was null for both. Product IDs, prospect import counts, and queued-retry counts: not run.
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
RESULT: Signals development summary lines: not run. Signals held-out: 12 pages, one run; summary lines: not run. Signal-run status, ranking status/tier, and draft status: not run.
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
RESULT: Replies development (36): per-label and per-difficulty accuracy, report path, and duration — not run. Replies held-out (24, one run): per-label and per-difficulty accuracy — not run.
```

## 6. Verify implementation without rerunning live or held-out evaluations

```bash
make verify
git diff --check
```

These checks use tests and mocked Ollama responses; they do not count as a live
model demonstration and do not rerun either held-out evaluator.

```text
RESULT: make verify — passed (152 tests); git diff --check — passed.
```
