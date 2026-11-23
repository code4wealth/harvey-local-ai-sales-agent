# CLAUDE.md — Project Memory for Claude Code

Project

Fork of ethanplusai/harvey, converted into a fully local, zero-LLM-cost, multi-product AI sales agent (EDXSO AI Engineer Intern — Assignment 2). Read docs/PRD.md first, then docs/WORKFLOWS.md, then docs/TASKS.md.

THE ONE RULE (automatic-fail if broken)

All AI inference goes through one file: app/llm_client.py, which talks ONLY to http://127.0.0.1:11434 (Ollama).

NEVER add OpenAI, Anthropic, Gemini, Codex, Cohere, Mistral API, Together, Groq, HuggingFace Inference, or any paid/cloud AI.
NEVER add a "fallback" to a cloud model. If Ollama is down: raise OllamaUnavailable, queue the task, show a clear error.
NEVER hard-code generated outputs (profiles, ICPs, signals, emails, labels). Outputs come from the model or from deterministic code at runtime.
NEVER put API keys in the repo. .env.example must contain no AI keys.
Web research (Scrapy/BS4/Playwright) is internet access but is NOT AI. Keep it in app/research/, separate from app/llm_client.py.

(Claude Code is only the development tool. The shipped app must have zero Claude/Anthropic/OpenAI references or dependencies. CLAUDE.md, AGENTS.md, .claude/ are excluded from the verify scan; delete them before final submission if you prefer.)

Stack

Python 3.11+, FastAPI, SQLite (stdlib sqlite3), httpx, Ollama + Qwen3 (Apache-2.0), sentence-transformers (all-MiniLM-L6-v2), Scrapy/BeautifulSoup/Playwright (research only), Harvey's existing frontend or React (Vite).

Layout (target)
app/
  main.py            FastAPI app + routes
  llm_client.py      ONLY AI path (Ollama localhost)
  hardware.py        RAM/CPU/GPU detect + model recommendation
  db.py              SQLite schema + helpers (inference_log, task_queue)
  queue_worker.py    retries queued tasks when Ollama returns
  embeddings.py      sentence-transformers (offline-safe)
  scoring.py         deterministic hybrid scoring
  workflows/         profile.py icp.py research.py signals.py problem.py email.py reply.py
  research/          web scraping (internet, non-AI)
data/                SAMPLE data: company_info/, product-scoped prospects/, prospect_pages/, sample/replies.csv (text-only), eval/ (offline ground truth)
frontend/            dashboard
scripts/             verify_no_cloud.py, offline_test.py, eval_replies.py
tests/
docs/                PRD, ARCHITECTURE, WORKFLOWS, TASKS, ACCEPTANCE_CHECKLIST + deliverable docs
test_evidence/

Commands
ollama serve                         # start local inference
ollama pull qwen3:4b                 # laptop model (qwen3:8b / 14b for stronger machines)
uvicorn app.main:app --reload        # backend
pytest -q                            # tests
python scripts/verify_no_cloud.py    # MUST pass before every commit
python scripts/offline_test.py       # runs full pipeline, prints inference log
make verify                          # verify + tests

Coding conventions

Type hints, small functions, pydantic models for every LLM JSON output (validate; retry up to 2x on invalid JSON).
Qwen3: send "think": false; also strip <think>...</think> defensively.
Every LLM call must write a row to inference_log (task, model, host, prompt/eval tokens, seconds, timestamp).
Every signal must include an evidence quote; code verifies the quote exists in source text, otherwise drop it.
Scoring is deterministic code (works with Ollama down). LLM may only add a text rationale.
Any mocked/sample data must be labelled SAMPLE in files and in the UI.
Secrets only via env vars; never commit .env.

Working agreement

Work phase by phase from docs/TASKS.md; tick checkboxes as you finish.
After each phase: run make verify, commit with a clear message.
Before inventing structure, inspect Harvey's existing code and adapt to it.
Ask me before adding any new dependency; list its licence.
Prefer simple and reliable over clever. Small models need short prompts, an example output, and retries.
