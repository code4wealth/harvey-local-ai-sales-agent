# Models and dependency licences

This is a working inventory for the Phase 2 baseline. Confirm the exact
installed distribution licence metadata and any model-card changes before a
release; dependency ranges are intentionally not pinned to exact versions
until they have been installed and tested on the target machine.

## Local models

| Component | Intended licence | Use | Network behaviour |
|---|---|---|---|
| Qwen3 (recommended default family) | Apache-2.0 | Text inference through Ollama on this machine | Model files are downloaded before offline use; inference goes only to `http://127.0.0.1:11434` |
| `all-MiniLM-L6-v2` | Apache-2.0 | Local text embeddings (implemented in the deterministic batch) | Model files are downloaded/cached before offline use; embedding inference is local |

## Python dependencies

| Distribution | Intended licence | Role |
|---|---|---|
| FastAPI | MIT | HTTP API |
| Uvicorn | BSD-3-Clause | ASGI server |
| HTTPX | BSD-3-Clause | Requests to local Ollama |
| Pydantic | MIT | Validation and structured outputs |
| sentence-transformers | Apache-2.0 | Local embeddings (Phase 4) |
| `huggingface_hub` (transitive dependency of sentence-transformers) | Apache-2.0 | Downloads and caches model files; it is not an inference endpoint and is not used to run cloud inference |
| Beautiful Soup 4 | MIT | HTML parsing for public-web research (research only, Phase 4) |
| pytest | MIT | Test runner |

The local inference path does not use a hosted model endpoint. After model
files have been downloaded and cached, the embedding model is intended to run
with `HF_HUB_OFFLINE=1`; Ollama inference stays on loopback.

`sentence-transformers` and its large tensor-runtime dependencies have not
been installed in the Phase 2 sandbox, so exact resolved versions and
transitive licences will be checked after the user's target-machine install.

The repository's application licence is AGPL-3.0-only; see `LICENSE` and
`NOTICE` for upstream attribution and the earlier MIT-licensed upstream code.
