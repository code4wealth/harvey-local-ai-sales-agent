# Models, libraries, and dependency licences

This inventory distinguishes checked-in requirements, package metadata observed in
the sandbox `.venv`, earlier operator-reported facts, and items not independently
confirmed. **VERIFY** means the exact artifact, resolved target version, or
licence text still needs inspection before redistribution or a release. Python
distribution metadata is not a substitute for checking separately downloaded
model weights. The sandbox inspection does not establish the Windows target's
resolved dependency set.

The current sandbox `.venv` does **not** contain `sentence-transformers`,
Ollama, PowerShell, or model files. Tests use mocked Ollama responses and fake
embeddings; they do not establish licences for the model artifacts or perform a
live model run.

## Harvey and upstream notice

The upstream Harvey/Sellbird project is licensed `AGPL-3.0-only` starting
with upstream version 0.4.0. This fork keeps that licence: `pyproject.toml`
declares `AGPL-3.0-only`, and the repository `LICENSE` contains the AGPL-3.0
text. `NOTICE` preserves the upstream attribution and explains that older
upstream releases through 0.3.x were MIT-licensed. Keep both `LICENSE` and
`NOTICE` with distributions. This project notice does not grant or verify
licences for third-party models or packages.

## Core runtime and UI licence summary

The following application components are called out explicitly. Sandbox package
metadata and lockfile observations are not a substitute for checking the exact
Windows installation, bundled notices, and deployment versions; mark unresolved
target artifacts **VERIFY**.

| Component | Role | Licence evidence and target status |
|---|---|---|
| FastAPI (`fastapi`) | Local API framework | MIT in observed Python metadata; target resolution/licence **VERIFY**. |
| Uvicorn (`uvicorn`) | Local ASGI server | BSD-3-Clause in observed Python metadata; target resolution/licence **VERIFY**. |
| SQLite (`sqlite3` Python wrapper and linked SQLite runtime) | Local database storage | **VERIFY** — linked runtime version and applicable target distribution notice were not inspected. |
| Sentence-Transformers (`sentence-transformers`) | Local embedding package | Apache-2.0 was previously operator-reported, not independently confirmed here; target version/licence **VERIFY**. The model weights have a separate `VERIFY` entry below. |
| BeautifulSoup (`beautifulsoup4`) | Stored HTML parsing and optional public-page helper | MIT in observed Python metadata; target resolution/licence **VERIFY**. |
| Requests (`requests`) | Optional public-page helper HTTP client | Apache-2.0 in observed Python metadata; target resolution/licence **VERIFY**. |
| Pydantic (`pydantic`) | Structured request/response validation | MIT in observed Python metadata; target resolution/licence **VERIFY**. |
| React (`react`, `react-dom`) | Dashboard UI runtime | MIT in `frontend/package-lock.json` metadata (`19.3.1`); exact deployed bundle and target notices **VERIFY**. |

## Models and local runtime

The hardware selector in `app/hardware.py` can recommend the Qwen3 tags below;
`DEFAULT_MODEL` may override that recommendation. Each tag names a distinct
Ollama artifact, and its manifest/model-card licence and exact pulled digest
must be checked separately.

| Model or runtime | Use / observed identifier | Licence and verification status |
|---|---|---|
| Qwen3 `qwen3:1.7b` | Low-resource generation recommendation | **VERIFY** — artifact licence, manifest, and digest were not inspected. |
| Qwen3 `qwen3:4b` | Standard-laptop generation recommendation; an earlier operator report named digest `359d7dd4bcda` and size 2.5 GB | **VERIFY** — Apache-2.0 was operator-reported, not independently checked against the exact artifact/model card. |
| Qwen3 `qwen3:8b` | Standard-plus generation recommendation | **VERIFY** — artifact licence, manifest, and digest were not inspected. |
| Qwen3 `qwen3:14b` | High-performance generation recommendation | **VERIFY** — artifact licence, manifest, and digest were not inspected. |
| Custom `DEFAULT_MODEL` tag | Optional operator override | **VERIFY** — identify and review the exact model artifact and licence before use. |
| `sentence-transformers/all-MiniLM-L6-v2` | Local embeddings; model revision is not pinned in the application | **VERIFY** — model revision, downloaded files, and model-card licence were not inspected. This is separate from the Python `sentence-transformers` package licence. |
| Ollama | Local model server at the fixed loopback URL in `app/llm_client.py`; `0.40.17` is an earlier operator-reported version | **VERIFY** — installed version and distribution licence were not inspected in this update. |

Model files must be present in the local Ollama or Hugging Face cache before
use. The embedding loader sets `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`; `OFFLINE_STRICT=1` additionally disables Hub telemetry
and implicit-token use. These flags do not determine a model's licence or verify
that all package code is free of network behavior.

## Declared Python dependencies

Version ranges are from `pyproject.toml` (mirrored by `requirements.txt`). The
observed versions and licence strings below came from distribution metadata in
the repository sandbox `.venv`; they are not a Windows lockfile. **VERIFY** the
resolved versions and licence notices in the actual deployment environment.

| Distribution | Declared role / version range | Sandbox observation | Licence status |
|---|---|---|---|
| `fastapi` | Runtime API; `>=0.115,<1` | `0.165.0` | MIT in observed metadata; target resolution **VERIFY**. |
| `uvicorn` | Runtime ASGI server; `>=0.34,<1` | `0.54.0` | BSD-3-Clause in observed metadata; target resolution **VERIFY**. |
| `httpx` | Runtime HTTP client for local Ollama; `>=0.27.0,<1` | `0.28.1` | BSD-3-Clause in observed metadata; target resolution **VERIFY**. |
| `pydantic` | Runtime data/schema validation; `>=2.5,<3` | `2.14.4` | MIT in observed metadata; target resolution **VERIFY**. |
| `sentence-transformers` | Runtime local embeddings; `>=2.7,<4` | Not installed; `3.4.1` / Apache-2.0 was previously operator-reported | **VERIFY** — package version and licence metadata were not independently confirmed here. |
| `beautifulsoup4` | Runtime parsing of stored page text and optional online page-text extraction; `>=4.12.3,<5` | `4.15.0` | MIT License in observed metadata; target resolution **VERIFY**. |
| `requests` | Optional public-page helper HTTP client; `>=2.31,<3` | `2.34.2` | Apache-2.0 in observed metadata; target resolution **VERIFY**. Used only when the separate online collector is explicitly run, not by local inference. |
| `pytest` | Development/test dependency; `>=8.0,<9` | `8.4.2` | MIT in observed metadata; target resolution **VERIFY**. |
| `setuptools` | PEP 517 build backend; `>=68.0` | Sandbox has `66.1.1`, below the declared minimum | Metadata did not declare a licence; build resolution and licence **VERIFY**. |

## Major framework and test transitive dependencies

These packages were present in the sandbox `.venv` as transitive dependencies.
Their versions and licence identifiers are observations from local package
metadata, not the target Windows resolution. Every row's target version/licence
status is therefore explicitly **VERIFY**.

| Distribution | Observed version | Observed licence metadata | Target status | Main dependency path |
|---|---:|---|---|---|
| `starlette` | `1.10.0` | BSD-3-Clause | **VERIFY** | FastAPI / ASGI web layer |
| `anyio` | `4.16.0` | MIT | **VERIFY** | FastAPI, Starlette, and HTTPX async compatibility |
| `annotated-doc` | `0.0.7` | MIT | **VERIFY** | FastAPI |
| `opentelemetry-api` | `1.45.2` | Apache-2.0 | **VERIFY** | FastAPI metadata dependency |
| `typing-inspection` | `0.4.5` | MIT | **VERIFY** | FastAPI / Pydantic |
| `pydantic-core` | `2.50.5` | MIT | **VERIFY** | Pydantic validation core |
| `annotated-types` | `0.8.0` | MIT | **VERIFY** | Pydantic |
| `typing-extensions` | `4.16.0` | PSF-2.0 | **VERIFY** | Framework and validation compatibility |
| `httpcore` | `1.0.9` | BSD-3-Clause | **VERIFY** | HTTPX transport |
| `certifi` | `2026.11.20` | MPL-2.0 | **VERIFY** | HTTPX certificate bundle |
| `idna` | `3.20` | BSD-3-Clause | **VERIFY** | HTTPX URL handling |
| `click` | `8.5.1` | BSD-3-Clause | **VERIFY** | Uvicorn command-line interface |
| `h11` | `0.16.0` | MIT | **VERIFY** | Uvicorn HTTP/1.1 implementation |
| `soupsieve` | `2.10` | MIT | **VERIFY** | BeautifulSoup selector support |
| `packaging` | `26.4` | Apache-2.0 OR BSD-2-Clause | **VERIFY** | Test/build tooling |
| `iniconfig` | `2.3.1` | MIT | **VERIFY** | Pytest |
| `pluggy` | `1.7.0` | MIT | **VERIFY** | Pytest plugin system |
| `Pygments` | `2.21.0` | BSD-2-Clause | **VERIFY** | Pytest output support |

## Major embedding-stack dependencies not resolved here

The embedding runtime was not installed in the sandbox `.venv`. The following
major dependencies are expected through `sentence-transformers` and its model
loading stack; exact selection can vary by version, Python, platform, and
installed extras. No exact version or licence metadata was inspected here, so
each remains **VERIFY** for the target environment.

| Distribution / library | Role | Version and licence status |
|---|---|---|
| `transformers` | Tokenization and model-loading stack | **VERIFY** |
| `huggingface-hub` | Local model cache and model metadata client | **VERIFY** |
| `torch` | Tensor execution backend | **VERIFY** |
| `tokenizers` | Transformer tokenization backend | **VERIFY** |
| `numpy` | Array operations | **VERIFY** |
| `scipy` | Scientific/numerical operations | **VERIFY** |
| `scikit-learn` | Sentence-Transformers utilities | **VERIFY** |
| `Pillow` | Image utilities exposed by the model stack | **VERIFY** |
| `safetensors` | Optional/supported model-weight serialization | **VERIFY** |
| `tqdm` | Progress reporting | **VERIFY** |
| `filelock`, `fsspec`, `requests`, `regex`, `PyYAML` | Supporting model-cache/loading dependencies, depending on resolution | **VERIFY** |

## System and optional tools

- Python `>=3.11` is the project runtime. Its standard-library modules (including
  `sqlite3` and `ctypes`) are not separately declared Python distributions. The
  Python build and linked SQLite version/licence on the target system are
  **VERIFY**.
- `nvidia-smi` is an optional external NVIDIA utility used only to read GPU
  memory. Driver/tool version and licence were not inspected: **VERIFY**.
- The PowerShell acceptance scripts use .NET `System.Net.Http`; the target
  PowerShell/.NET versions and their deployment notices are **VERIFY**.
- Scrapy and Playwright are not declared or used by the current application.
  The app does not crawl or browser-automate public sites.

No paid inference API or hosted model service is a dependency. All model
inference is intended for local Ollama, and embeddings use the cached local
model. That architecture does not remove the need to verify each selected model
and third-party component's licence before distribution.
