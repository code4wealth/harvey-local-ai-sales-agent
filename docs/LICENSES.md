# Licence and version inventory

Python versions and licence fields below are from `importlib.metadata` in the
repository sandbox (`License-Expression` where present, otherwise `License`).
They describe that sandbox, not the target Windows laptop.
The Ollama executable is unavailable in this environment, so `ollama --version`
and `ollama list` could not run. No model-card licence was available locally.
Unverified items are marked explicitly; no licence is inferred for them.

## Models and runtime

| Component | Version / identifier | Licence | Role / evidence |
|---|---|---|---|
| Harvey Local AI Sales Agent | `0.1.0` (`pyproject.toml`) | `AGPL-3.0-only` | Application; `LICENSE` and upstream `NOTICE` are retained. |
| Ollama | not run — executable unavailable | not run — local distribution metadata unavailable | Local model server; the app targets loopback only. |
| Qwen3 | `qwen3:4b` tag; local model listing not run | verify at model card; not run | Local text generation model; model card was not readable in this environment. |
| `sentence-transformers/all-MiniLM-L6-v2` | not run — model not locally available | verify at model card; not run | Local embedding model; no model-card metadata was available locally. |

## Python distributions

| Distribution | Version | Licence metadata (`License-Expression` / `License`) | Role / status |
|---|---:|---|---|
| `fastapi` | `0.165.0` | MIT | API framework. |
| `uvicorn` | `0.54.0` | BSD-3-Clause | ASGI server. |
| `httpx` | `0.28.1` | BSD-3-Clause | Fixed loopback Ollama transport. |
| `pydantic` | `2.14.4` | MIT | Structured request/response validation. |
| `starlette` | `1.10.0` | BSD-3-Clause | FastAPI's ASGI/web dependency. |
| `beautifulsoup4` | `4.15.0` | MIT License | Declared dependency; HTML parsing. |
| `pytest` | `8.4.2` | MIT | Declared development/test dependency. |
| `sentence-transformers` | not run — not installed | not run — no local package metadata | Declared dependency for offline local embeddings; its model files must be cached before use. |
| `huggingface-hub` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; its transitive role/licence must be confirmed after dependency installation. |
| `numpy` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `transformers` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `tokenizers` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `torch` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `scrapy` | not run — not installed or declared | not run — not a project dependency | Not used by the current application. |
| `playwright` | not run — not installed or declared | not run — not a project dependency | Not used by the current application. |

The declared runtime and development dependencies are listed in
`pyproject.toml` and `requirements.txt`. `sentence-transformers` is declared
but was not installed in this sandbox; exact resolved versions and licences for
it and its transitive packages must be checked on the target installation.
Scrapy and Playwright are not declared by this repository. This project is an
AGPL-3.0-only derivative; retain `LICENSE` and `NOTICE` with distributions.
