# Harvey — Local Multi-Product AI Sales Agent

A fully local, zero-LLM-cost, multi-product AI sales agent. Fork of
[ethanplusai/harvey](https://github.com/ethanplusai/harvey) (now Sellbird),
rebuilt to run **entirely on your machine**: Ollama + Qwen3 for all AI
inference, SQLite for storage, FastAPI + a vanilla-JS dashboard, and
sentence-transformers for embeddings. No API keys, no per-token billing, no
cloud inference — ever.

> Upstream attribution: Harvey/Sellbird was created by Ethan Rogers and the
> Sellbird contributors, AGPL-3.0-only (earlier releases MIT). See `NOTICE` and
> `LICENSE`. This fork removes the upstream subscription-CLI architecture
> entirely and replaces it with local-only inference.

## Status

Early conversion in progress — see `docs/TASKS.md` for the phase checklist
and `docs/HARVEY_NOTES.md` for what changed versus upstream.

## How it works

- All AI inference goes through one file, `app/llm_client.py`, which talks
  only to `http://127.0.0.1:11434` (Ollama). If Ollama is down, AI tasks are
  queued and deterministic features keep working.
- Web research (BeautifulSoup over already-downloaded pages) is internet
  access, never AI, and lives in `app/research/`, fully separated from
  `app/llm_client.py`.
- Sample data in `data/` is **SAMPLE** and labelled as such everywhere.

## Quickstart

```bash
ollama serve                      # start local inference
ollama pull qwen3:4b              # laptop model (qwen3:8b / qwen3:14b for stronger machines)
pip install -e .
uvicorn app.main:app --reload     # backend + dashboard
pytest -q                         # tests (LLM mocked; no Ollama needed)
python scripts/verify_no_cloud.py # guard: fails if any cloud-AI reference reappears
```

## Licence

AGPL-3.0-only. See `LICENSE`, `NOTICE`.
