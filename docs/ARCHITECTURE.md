# Architecture

## Components

```text
Frontend (local Harvey UI)
        | HTTP
FastAPI (app/main.py) --> Orchestrator (app/pipeline.py)
        |                      +- workflows/* --> app/llm_client.py --> Ollama @127.0.0.1:11434 [ONLY AI PATH]
        |                      +- embeddings.py -> local model cache (future, approval required)
        |                      +- scoring.py (deterministic)
        |                      +- research/ (public web only; NOT AI)
        +--> SQLite: products, business_profiles, icps, prospects, signals,
                     problem_statements, scores, generated_emails, replies,
                     inference_log, task_queue

Queue worker: claims task_queue work; retries when local Ollama is unavailable.
```

`app/research/` may access the public internet but must never import `app/llm_client.py`. The inference client may access only `http://127.0.0.1:11434` and must never import research code. The UI and API use relative URLs to the local backend.

## Data flow per prospect

Local page text → research summary (local LLM) + optional local embedding similarity → signals (LLM plus evidence verification) → grounded problem statement (LLM) → deterministic score → generated email (LLM). Replies are classified independently. No workflow sends email.

## Failure matrix

| Failure | Behavior |
|---|---|
| Ollama unavailable | Raise `OllamaUnavailable`, queue AI task, show clear status; deterministic features continue |
| Model not downloaded | Show a helpful `ollama pull <model>` instruction; retain a visible failure/queued state |
| Invalid JSON | Retry at most twice, then fail the step with an actionable error |
| Timeout | Mark the step failed or queued according to the failure class; allow retry |
| Local embedding model unavailable offline | Clear error; skip similarity and flag the zero contribution (future phase) |

Every inference call writes task, model, fixed host, token counts when reported, latency, timestamp, status, and any error to `inference_log`. SQLite `task_queue` is distinct from any email outbox; no mail-sending subsystem is part of this product.
