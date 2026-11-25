# Architecture

```text
Local browser / API client
        | HTTP to FastAPI
FastAPI (app/main.py)
  |-- workflows/{pipeline,profile,icp,signals,replies,draft,problem_statement}
  |       `-- llm_client.py --> Ollama @127.0.0.1:11434  [ONLY AI PATH]
  |-- ranking.py / scoring.py                 [model inputs + rule-based scoring]
  |-- embeddings.py --> sentence-transformers [local model cache]
  `-- SQLite: products, business_profiles, icps, prospects, signal_runs,
              signals, scores, reply_classifications, draft_runs,
              workflow_runs, inference_log, task_queue

Separate, operator-invoked online helper (not part of FastAPI):
scripts/fetch_public_pages.py --CSV URLs--> requests + robots.txt checks
                                      `--> data/prospect_pages/ [stored text]
```

The optional `scripts/fetch_public_pages.py` helper can fetch only explicit
public URLs when manually run. It uses Requests and BeautifulSoup, checks
`robots.txt`, and writes text under `data/prospect_pages/`; it must never import
`app.llm_client` or call local inference. AI workflows read stored page text
only. The local inference client is hard-coded to loopback Ollama. There is no
cloud fallback.

## Runtime boundaries

- Product and prospect records are isolated by `product_id`.
- Local profile and ICP workflows use stored product information. Signal
  extraction uses the explicitly stored local prospect page. Every response is
  schema-validated; signal evidence must be an exact quote in the stored page,
  and quote/schema failures share one stricter retry. Invalid evidence is never
  persisted as a successful signal.
- `GET /api/products/{product_id}/ranking` uses the product's stored ICP, local
  page text, and only validated signals from each prospect's latest successful
  signal run. Embedding similarity and signal types/confidences are
  model-derived inputs; fit heuristics, quote checks, weighting, tiering, and
  evidence-quality audit are rule-based. A later failed run is reported but
  does not replace the last successful signal snapshot.
- Reply classification uses only the stored reply text. `data/eval/` labels
  never enter the application database or runtime prompts.
- Draft generation uses only a stored profile and signal quotes rechecked
  against the prospect's current stored page text. Each cited span must be a
  substring of both that page and verified signal evidence, and appear quoted
  in the body. Drafts are stored in `draft_runs`, never sent; missing/stale
  evidence is persisted as skipped with a reason and no inference call.
- All AI inference uses `app/llm_client.py`. Each `inference_log` row records
  model, local host, token counts, latency, the actual temperature/seed/repeat
  penalty for that request, status, rendered-prompt SHA-256, and source commit.
  Workflow result payloads also retain their prompt hash and commit beside the
  model settings; older migrated rows use empty hashes until regenerated.
- `GET /health` checks API/SQLite liveness only. Ollama availability is reported
  separately by `GET /api/status`, so local AI downtime does not mark the whole
  service unhealthy or block deterministic features.

## Determinism and failure handling

The first inference request uses temperature `0` and seed `42`; the single
validation retry uses temperature `0.2` and the next seed. Every request uses
repeat penalty `1.0`, explicit context budgets, JSON-schema mode, and Pydantic
validation. Workflow validators also reject unsupported source claims. A
stricter prompt is used on the retry; if the second response is still invalid,
the workflow fails with the validation reason. Signal quote verification uses
that same two-attempt limit. `think=false` is always set by the Ollama client.

The persistent queue worker replays LLM-dependent tasks after Ollama recovers.
Connection failures become `OllamaUnavailable` and are queued; timeouts remain
distinct. Deterministic queue handlers do not require an Ollama health probe.
Terminal validation errors are persisted. Email is never transmitted.

`inference_log.status` is one of `ok`, `error:unavailable`, `error:timeout`,
`error:http`, or `error:invalid_json`; inference-proof views should filter to
`ok`.

## Data flow

```text
Product docs -> profile -> ICP
Local prospect page -> verified signals -> deterministic product ranking
                                   \-> grounded, persisted, unsent draft
Text-only reply -> eight-way reply classification
```

Embeddings and heuristic ranking are local. Reply evaluation labels are kept
under `data/eval/`, separate from sample reply text in `data/sample/`. The
reply evaluator defaults to the development split, writes redacted metrics
under `test_evidence/real_run/`, and requires a matching frozen prompt hash
before it can load held-out labels or text. See `docs/WORKFLOWS.md` and
`docs/KNOWN_LIMITATIONS.md` for detailed contracts and caveats.
