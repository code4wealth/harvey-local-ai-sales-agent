# Architecture

```text
Local browser / API client
        | HTTP to FastAPI
FastAPI (app/main.py)
  |-- workflows/{profile,icp,signals,replies,draft}
  |       `-- llm_client.py --> Ollama @127.0.0.1:11434  [ONLY AI PATH]
  |-- ranking.py / scoring.py                 [deterministic]
  |-- embeddings.py --> sentence-transformers [local model cache]
  |-- research/                                [internet-capable, not AI]
  `-- SQLite: products, business_profiles, icps, prospects, signal_runs,
              signals, scores, reply_classifications, draft_runs,
              workflow_runs, inference_log, task_queue
```

`app/research/` may fetch public web pages but must never import
`llm_client.py`. The local inference client must never import research and is
hard-coded to the loopback Ollama endpoint. There is no cloud fallback.

## Runtime boundaries

- Product and prospect records are isolated by `product_id`.
- Local profile and ICP workflows use stored product information. Signal
  extraction uses the explicitly stored local prospect page. Failed quote
  verification triggers up to two same-prompt retries; the attempt with the
  most verified signals is persisted, with evidence quotes left untouched.
- `GET /api/products/{product_id}/ranking` is deterministic. It uses the
  product's stored ICP, local page text, and only validated signals from each
  prospect's latest successful signal run. A later failed run is reported but
  does not replace the last successful signal snapshot.
- Reply classification uses only the stored reply text. `data/eval/` labels
  never enter the application database or runtime prompts.
- Draft generation uses only a stored profile and verified signal evidence.
  Drafts are stored in `draft_runs`, never sent; no-verified-evidence cases
  are persisted as skipped without an inference call.
- All AI inference uses `app/llm_client.py` and records model, local host,
  token counts, latency, temperature, seed, repeat penalty, and status in `inference_log`.

## Determinism and failure handling

Structured inference requests use temperature `0`, seed `42`, explicit context
budgets, JSON-schema mode, and Pydantic validation. Workflow validators can
reject schema-valid but ungrounded output and receive the same maximum of two
retries. `think=false` is always set by the Ollama client.

The persistent queue worker replays LLM-dependent tasks after Ollama recovers.
Connection failures become `OllamaUnavailable` and are queued; timeouts remain
distinct. Deterministic queue handlers do not require an Ollama health probe.
Invalid JSON after retries is persisted as a failed workflow result. Email is
never transmitted.

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
