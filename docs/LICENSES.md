# Licence and version inventory

Python package versions and licence fields below are from `importlib.metadata`
in the repository sandbox (`License-Expression` where present, otherwise
`License`) or are transcribed from the user-supplied command outputs noted in
the table. Sandbox metadata describes that environment, not the target laptop.
No files were present under `test_evidence/offline/` for this update; the Ollama
and package facts supplied here are not live acceptance evidence. No additional
version or licence has been inferred.

## Models and runtime

| Component | Version / identifier | Licence | Role / evidence |
|---|---|---|---|
| Harvey Local AI Sales Agent | `0.1.0` (`pyproject.toml`) | `AGPL-3.0-only` | Application; `LICENSE` and upstream `NOTICE` are retained. |
| Ollama | `0.40.17` (user-supplied `ollama --version`) | not run — no Ollama distribution licence supplied | Local model server; the app targets loopback only. |
| Qwen3 | `qwen3:4b`; ID `359d7dd4bcda`; 2.5 GB (user-supplied `ollama list`) | Apache License, Version 2.0, January 2004 (user-supplied `ollama show qwen3:4b --license`) | Local text generation model; tag and model licence are user-reported. |
| `sentence-transformers/all-MiniLM-L6-v2` | not run — the supplied package version is not a model revision | not run — no model-card licence supplied | Local embedding model; model files must be cached before use. |

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
| `sentence-transformers` | `3.4.1` (user-supplied `pip show`) | Apache 2.0 (user-supplied `pip show`) | Declared dependency for offline local embeddings; its model files must be cached before use. |
| `huggingface-hub` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; its transitive role/licence must be confirmed after dependency installation. |
| `numpy` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `transformers` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `tokenizers` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `torch` | not run — not installed | not run — no local package metadata | Not installed in this sandbox; may be part of the embedding runtime. |
| `scrapy` | not run — not installed or declared | not run — not a project dependency | Not used by the current application. |
| `playwright` | not run — not installed or declared | not run — not a project dependency | Not used by the current application. |

The declared runtime and development dependencies are listed in
`pyproject.toml` and `requirements.txt`. The `sentence-transformers` version
and licence above are user-supplied `pip show` facts; exact resolved versions
and licences for its transitive packages remain `not run`. Scrapy and
Playwright are not declared by this repository. This project is an
AGPL-3.0-only derivative; retain `LICENSE` and `NOTICE` with distributions.
