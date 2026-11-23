Architecture
Frontend (Harvey UI / React)
        | HTTP
FastAPI (app/main.py) --> Orchestrator (pipeline.py)
        |                      +- workflows/* --> llm_client.py --> Ollama @127.0.0.1:11434   [ONLY AI PATH]
        |                      +- embeddings.py -> sentence-transformers (local cache)
        |                      +- scoring.py (deterministic)
        |                      +- research/ (Scrapy/BS4/Playwright)  [internet, NOT AI]
        +--> SQLite: products, business_profiles, icps, prospects, signals, problem_statements,
                     scores, emails, replies, inference_log, task_queue
Queue worker: polls task_queue; when Ollama is up, replays tasks.
Separation principle
app/research/ may touch the internet and must never import llm_client. llm_client may only touch localhost and must never import research.
Data flow per prospect
local page text -> research summary (LLM) + similarity (embeddings) -> signals (LLM + evidence verification) -> problem statement (LLM) -> score (code) -> email (LLM). Replies are classified independently.
Failure matrix
Failure	Behaviour
Ollama down	OllamaUnavailable, task queued, UI banner, deterministic features work
Model not pulled	Error with ollama pull <model> hint
Invalid JSON	Retry ×2 then fail the step with message
Timeout	Step marked failed, retry button
Embedding model missing offline	Clear error; similarity step skipped, score uses 0 for that term and flags it
