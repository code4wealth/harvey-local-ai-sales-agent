# Licence and version inventory

Python package versions and licence fields already recorded below came from
`importlib.metadata` in the repository sandbox (`License-Expression` where
present, otherwise `License`); they describe that sandbox, not the target
laptop. No files were present under `test_evidence/offline/` for this update.
The command-output block supplied with the request contained a placeholder, not
captured output, for `ollama --version`, `ollama list`,
`ollama show qwen3:4b --license`, and `pip show sentence-transformers`. Those
values therefore remain `not run`; no version or licence has been inferred.

## Models and runtime

| Component | Version / identifier | Licence | Role / evidence |
|---|---|---|---|
| Harvey Local AI Sales Agent | `0.1.0` (`pyproject.toml`) | `AGPL-3.0-only` | Application; `LICENSE` and upstream `NOTICE` are retained. |
| Ollama | not run — no `ollama --version` output supplied | not run — no local licence output supplied | Local model server; the app targets loopback only. |
| Qwen3 | `qwen3:4b` tag specified for the demo; installed tag not run | not run — no `ollama show qwen3:4b --license` output supplied | Local text generation model; local installation and model-card licence remain unverified. |
| `sentence-transformers/all-MiniLM-L6-v2` | not run — no local model/version evidence supplied | not run — no model-card licence evidence supplied | Local embedding model; model files must be cached before use. |

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
| `sentence-transformers` | not run — no `pip show sentence-transformers` output supplied | not run — no package metadata supplied | Declared dependency for offline local embeddings; its model files must be cached before use. |
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
