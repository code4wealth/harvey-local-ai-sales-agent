# Models, libraries, and dependency licences

This inventory separates repository notices, installed-package metadata, earlier
operator-reported facts, and items that remain unconfirmed. Python distribution
versions and licence fields were rechecked with `importlib.metadata` under the
sandbox's Python 3.11.2; React metadata and its local licence files were checked
from the locked frontend install. **VERIFY** means the exact model artifact,
linked target runtime, or target-Windows resolution/licence still needs review.
Sandbox package metadata does not establish the Windows dependency resolution,
and package licences do not establish the licences of separately downloaded
model weights.

The sandbox does **not** contain `sentence-transformers`, its embedding stack,
Ollama, PowerShell, or model files. Workflow tests use mocked Ollama responses
and fake embeddings; they do not establish model-artifact licences or perform a
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

The following application components are called out explicitly. The Python
values below come from the repository `.venv` (Python 3.11.2 on Linux); frontend
values come from `frontend/node_modules`. These observations do not establish
the exact Windows installation or deployed bundle. Mark unresolved target
artifacts **VERIFY**.

| Component | Role | Licence evidence and target status |
|---|---|---|
| FastAPI (`fastapi`) | Local API framework | MIT in observed Python metadata; target resolution/licence **VERIFY**. |
| Uvicorn (`uvicorn`) | Local ASGI server | BSD-3-Clause in observed Python metadata; target resolution/licence **VERIFY**. |
| SQLite (`sqlite3` Python wrapper and linked SQLite runtime) | Local database storage | Sandbox runtime version `3.40.1` observed via `sqlite3.sqlite_version`; target runtime and applicable licence/distribution notice **VERIFY**. |
| Sentence-Transformers (`sentence-transformers`) | Local embedding package | Not installed in this sandbox; `3.4.1` / Apache-2.0 is an earlier operator report, not independently confirmed. Target package version/licence **VERIFY**; the model weights have a separate **VERIFY** entry below. |
| BeautifulSoup (`beautifulsoup4`) | Stored HTML parsing and optional public-page helper | MIT in observed Python metadata; target resolution/licence **VERIFY**. |
| Requests (`requests`) | Optional public-page helper HTTP client | Apache-2.0 in observed Python metadata; target resolution/licence **VERIFY**. |
| Pydantic (`pydantic`) | Structured request/response validation | MIT in observed Python metadata; target resolution/licence **VERIFY**. |
| React (`react`, `react-dom`) | Dashboard UI runtime | Installed package metadata reports MIT at `19.3.1`; both package licence files and checked-in notices exist under `frontend/static/licenses/`. The exact deployed bundle/notice set **VERIFY**. |

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
the repository `.venv` under Python 3.11.2; they are not a Windows lockfile.
The recorded value is `License-Expression`, then `License`, then a `License :: ...`
classifier when neither field is supplied. **VERIFY** the
resolved versions and licence notices in the actual deployment environment.

| Distribution | Declared role / version range | Sandbox observation | Licence status |
|---|---|---|---|
| `fastapi` | Runtime API; `>=0.115,<1` | `0.165.0` | MIT in observed metadata; target resolution **VERIFY**. |
| `uvicorn` | Runtime ASGI server; `>=0.34,<1` | `0.54.0` | BSD-3-Clause in observed metadata; target resolution **VERIFY**. |
| `httpx` | Runtime HTTP client for local Ollama; `>=0.27.0,<1` | `0.28.1` | BSD-3-Clause in observed metadata; target resolution **VERIFY**. |
| `pydantic` | Runtime data/schema validation; `>=2.5,<3` | `2.14.4` | MIT in observed metadata; target resolution **VERIFY**. |
| `sentence-transformers` | Runtime local embeddings; `>=2.7,<4` | Not installed; `3.4.1` / Apache-2.0 was previously operator-reported | Target version/licence **VERIFY**; no local package metadata. |
| `beautifulsoup4` | Runtime parsing of stored page text and optional online page-text extraction; `>=4.12.3,<5` | `4.15.0` | MIT License in observed metadata; target resolution **VERIFY**. |
| `requests` | Optional public-page helper HTTP client; `>=2.31,<3` | `2.34.2` | Apache-2.0 in observed metadata; target resolution **VERIFY**. Used only when the separate online collector is explicitly run, not by local inference. |
| `pytest` | Development/test dependency; `>=8.0,<9` | `8.4.2` | MIT in observed metadata; target resolution **VERIFY**. |
| `setuptools` | PEP 517 build backend; `>=68.0` | Sandbox has `66.1.1`, below the declared minimum | No `License` field; MIT appears in its license classifier. Target build resolution/licence **VERIFY**. |

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
| `filelock`, `fsspec`, `regex`, `PyYAML` | Supporting model-cache/loading dependencies, depending on resolution | **VERIFY** |

## System and optional tools

- Python `>=3.11` is the project runtime; the sandbox used Python `3.11.2`.
  Its standard-library modules (including `sqlite3` and `ctypes`) are not
  separately declared Python distributions. The sandbox's linked SQLite runtime
  reported `3.40.1`; the target Windows Python build, linked SQLite version,
  and applicable distribution notice remain **VERIFY**.
- `nvidia-smi` is an optional external NVIDIA utility used only to read GPU
  memory. Driver/tool version and licence were not inspected: **VERIFY**.
- The PowerShell acceptance scripts use .NET `System.Net.Http`; the target
  PowerShell/.NET versions and their deployment notices are **VERIFY**.
- Scrapy and Playwright are not declared or used by the current application.
  The app does not crawl or browser-automate public sites.

## Exact external pages for remaining checks

These are official publisher/catalog/package pages for the operator to inspect
against the *actual target install*. They are review pointers only: none was
fetched or independently checked during this update, and a model-family card or
latest package page does not identify a local digest or target-resolved version.

### Models, Ollama, SQLite, and system tools

- **Ollama distribution/version:** [Ollama releases and installer versions](https://github.com/ollama/ollama/releases) and the [Ollama source licence](https://github.com/ollama/ollama/blob/main/LICENSE). Match the installed Windows version and its shipped notices.
- **Qwen3 local tags:** [Ollama Qwen3 library page](https://ollama.com/library/qwen3); source model cards: [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B), [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B), [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), and [Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B). Match the actual Ollama manifest, digest, and model terms; the source cards alone do not verify the packaged Ollama artifacts.
- **Embedding model:** [all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). Check the exact downloaded revision and its model-card licence separately from the Python package.
- **SQLite:** [SQLite copyright/licensing page](https://sqlite.org/copyright.html) and [Python `sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html). Record the SQLite version linked by the target Windows Python build and inspect that distribution's notices; the sandbox version is not a target confirmation.
- **PowerShell/.NET and NVIDIA tooling:** [PowerShell source licence](https://github.com/PowerShell/PowerShell/blob/master/LICENSE.txt), [.NET runtime licence](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT), and [NVIDIA driver downloads](https://www.nvidia.com/Download/index.aspx). Check the exact installed versions and accompanying terms/notices.

### Python package pages

The following official PyPI project pages are references for checking the target's
resolved package versions and licence metadata. Read the installed distribution
metadata on Windows as well; the project page's latest release is not a lockfile.

- Declared runtime/test/build packages: [fastapi](https://pypi.org/project/fastapi/), [uvicorn](https://pypi.org/project/uvicorn/), [httpx](https://pypi.org/project/httpx/), [pydantic](https://pypi.org/project/pydantic/), [sentence-transformers](https://pypi.org/project/sentence-transformers/), [beautifulsoup4](https://pypi.org/project/beautifulsoup4/), [requests](https://pypi.org/project/requests/), [pytest](https://pypi.org/project/pytest/), and [setuptools](https://pypi.org/project/setuptools/).
- Observed framework/test transitives: [starlette](https://pypi.org/project/starlette/), [anyio](https://pypi.org/project/anyio/), [annotated-doc](https://pypi.org/project/annotated-doc/), [opentelemetry-api](https://pypi.org/project/opentelemetry-api/), [typing-inspection](https://pypi.org/project/typing-inspection/), [pydantic-core](https://pypi.org/project/pydantic-core/), [annotated-types](https://pypi.org/project/annotated-types/), [typing-extensions](https://pypi.org/project/typing-extensions/), [httpcore](https://pypi.org/project/httpcore/), [certifi](https://pypi.org/project/certifi/), [idna](https://pypi.org/project/idna/), [click](https://pypi.org/project/click/), [h11](https://pypi.org/project/h11/), [soupsieve](https://pypi.org/project/soupsieve/), [packaging](https://pypi.org/project/packaging/), [iniconfig](https://pypi.org/project/iniconfig/), [pluggy](https://pypi.org/project/pluggy/), and [Pygments](https://pypi.org/project/Pygments/).
- Embedding-stack packages not installed in this sandbox: [transformers](https://pypi.org/project/transformers/), [huggingface-hub](https://pypi.org/project/huggingface-hub/), [torch](https://pypi.org/project/torch/), [tokenizers](https://pypi.org/project/tokenizers/), [numpy](https://pypi.org/project/numpy/), [scipy](https://pypi.org/project/scipy/), [scikit-learn](https://pypi.org/project/scikit-learn/), [Pillow](https://pypi.org/project/Pillow/), [safetensors](https://pypi.org/project/safetensors/), [tqdm](https://pypi.org/project/tqdm/), [filelock](https://pypi.org/project/filelock/), [fsspec](https://pypi.org/project/fsspec/), [regex](https://pypi.org/project/regex/), and [PyYAML](https://pypi.org/project/PyYAML/).

For the frontend, compare the locked package versions and checked-in notices with
[React](https://www.npmjs.com/package/react) and
[React DOM](https://www.npmjs.com/package/react-dom); verify that any deployed
bundle retains the corresponding third-party notices.

No paid inference API or hosted model service is a dependency. All model
inference is intended for local Ollama, and embeddings use the cached local
model. That architecture does not remove the need to verify each selected model
and third-party component's licence before distribution.
