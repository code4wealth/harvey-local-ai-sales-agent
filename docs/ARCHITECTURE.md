Architecture
Frontend (Harvey UI / React)
        | HTTP
FastAPI (app/main.py) --> Orchestrator (pipeline.py)
        |                      +- workflows/* --> llm_client.py --> Ollama @127.0.0.1:11434   [ONLY AI PATH]
        |                      +- embeddings.py -> sentence-transformers (local cache)
        |                      +- scoring.py (deterministic)
        |                      +- research/ (Scrapy/BS4/Playwright)  [internet, NOT AI]
        +--> SQLite: products, business_profiles, icps, prospects, signals, problem_statements,
                     prospect_research, scores, emails, replies, inference_log,
                     pipeline_runs, pipeline_steps, task_queue
Queue worker: polls task_queue; deterministic handlers run without Ollama, while LLM-dependent handlers wait for a healthy Ollama probe. Connection failures and model timeouts remain distinct in API status and inference_log.
Context budget: chat() defaults to num_ctx=4096 and temperature 0.2. Hardware recommendations are 2048 for low-resource, 4096 for standard tiers, and 8192 for high-performance; callers pass the recommended value. Research workflows should keep source-page input to roughly 2500 tokens before prompt construction.
inference_log.status: `ok`, `error:unavailable`, `error:timeout`, `error:http`, or `error:invalid_json`; inference-proof views should filter to `ok`.
Separation principle
app/research/ may touch the internet and must never import llm_client. llm_client may only touch localhost and must never import research.
Data flow per prospect
local page text -> research summary (LLM) + similarity (embeddings) -> signals (LLM + evidence verification) -> problem statement (LLM) -> score (code) -> email (LLM). Replies are classified independently.
Failure matrix
Failure	Behaviour
Ollama down	OllamaUnavailable, task queued, unavailable banner, deterministic features work
Model not pulled	Error with ollama pull <model> hint
Invalid JSON	Retry ×2 with validation feedback, then fail the step with message
Model timeout	OllamaTimeout, slow-model status, queued task retries
Embedding model missing offline	Similarity stays null; its weighted contribution is zero, listed in missing_components, and score is partial without re-normalization
