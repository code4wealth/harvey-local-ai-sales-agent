# Ollama outage and retry behavior

All model requests use the fixed loopback Ollama client in `app/llm_client.py`
(`http://127.0.0.1:11434`, `trust_env=False`). There is no cloud fallback. Local
embedding loads are also offline-only; model files must already be cached.

## During an outage

- `GET /api/status` reports Ollama as `available`, `unavailable`, `slow`, or
  `error`, and includes counts for `queued`, `running`, `done`, and `failed`
  tasks.
- A connection failure during an AI workflow is recorded as an
  `OllamaUnavailable` error. Profile, ICP, signal, draft, and reply-classification
  work is persisted with status `queued`, a queue-task ID, and an error field;
  their API response uses HTTP `202` and a JSON run/classification payload.
- Timeouts and invalid model responses remain distinct from connection
  failures. Invalid responses are validated and retried; a persistent failure
  remains visible in the stored run rather than silently switching providers.
- `GET /api/products/{product_id}/ranking` is deterministic and does not call
  Ollama. Missing or unavailable local embedding inputs remain partial/missing
  rather than being filled through a hosted service.

## Retry after Ollama returns

The lifespan-managed `QueueWorker` polls queued tasks automatically. If no task
runs (for example, because Ollama is still unavailable), it waits for its
configured poll interval before checking again. To request an immediate poll
without running task handlers in the API thread, call the local endpoint:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/queue/retry
```

The endpoint returns `status: scheduled` and current queue counts. Check
`GET /api/status` and the original workflow's `GET` route for its terminal run
status. Queue tasks are retained after completion/failure for diagnosis.

The dashboard's **Retry queued tasks** button calls the same endpoint. The
`test_evidence/offline/` acceptance scripts exercise the outage and recovery
path without recording reply or page text; see `docs/DEMO.md`.
