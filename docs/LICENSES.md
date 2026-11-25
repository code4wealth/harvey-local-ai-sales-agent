# Licence and version inventory

This inventory separates repository notices, installed-package metadata, and
operator-reported facts from items still unconfirmed. Python metadata was checked
in the repository `.venv` using Python 3.11.2 on Linux; frontend package metadata
and local notices were checked under `frontend/node_modules` and
`frontend/static/licenses/`. Those observations do not establish target Windows
resolution or deployed bundle contents. Every outstanding check is marked
**VERIFY**; a Python distribution's licence is not the licence of separately
downloaded model weights. Upstream Harvey/Sellbird is AGPL-3.0-only from
upstream version 0.4.0, as declared in `pyproject.toml` and `LICENSE`; older
upstream releases through 0.3.x remain under their historical MIT notice.

No Ollama executable, PowerShell, or model files are available for local
inspection. The owner reports target-Windows local inference and an offline
workflow run, but no corresponding capture files are present in this checkout;
those reports do not verify model or package licences. See
[`MODELS_AND_LICENCES.md`](MODELS_AND_LICENCES.md) for the detailed metadata,
remaining VERIFY inventory, and exact official pages to inspect.

## Models and runtime

| Component | Version / identifier | Licence | Verification status / role |
|---|---|---|---|
| Harvey Local AI Sales Agent | `0.1.0` (`pyproject.toml`) | `AGPL-3.0-only` | Verified from repository `LICENSE` and `NOTICE`; application. |
| Ollama | `0.40.17` (earlier user-reported `ollama --version`; not present here) | **VERIFY** | Match the installed Windows build to its shipped notices and official source licence before distribution. |
| Qwen3 tags | `qwen3:1.7b`, `qwen3:4b`, `qwen3:8b`, `qwen3:14b` are hardware-selector recommendations; `qwen3:4b` digest `359d7dd4bcda` and 2.5 GB were earlier user-reported | **VERIFY** | Review the exact local Ollama manifest/digest and model terms; the earlier Apache-2.0 report is unconfirmed. |
| `sentence-transformers/all-MiniLM-L6-v2` | Model revision **VERIFY** | **VERIFY** — model-card licence/revision not inspected | Local embedding model; check the exact downloaded files and card separately from the Python package licence. |

## Python distributions

The following versions and licence identifiers are environment metadata from
the repository `.venv` (Python 3.11.2). We recorded `License-Expression`, then
`License`, then a declared `License :: ...` classifier if neither field was
present. These are not the exact versions resolved on the target Windows
machine; target resolution/licence checks remain **VERIFY**.

| Distribution | Observed version | Observed licence metadata | Verification status / role |
|---|---:|---|---|
| `fastapi` | `0.165.0` | MIT | Sandbox metadata; target resolution **VERIFY**. API framework. |
| `uvicorn` | `0.54.0` | BSD-3-Clause | Sandbox metadata; target resolution **VERIFY**. ASGI server. |
| `httpx` | `0.28.1` | BSD-3-Clause | Sandbox metadata; target resolution **VERIFY**. Fixed loopback Ollama transport. |
| `pydantic` | `2.14.4` | MIT | Sandbox metadata; target resolution **VERIFY**. Structured request/response validation. |
| SQLite (`sqlite3` Python wrapper and linked runtime) | Sandbox linked runtime `3.40.1`; target **VERIFY** | Licence/distribution notice **VERIFY** | The local version was observed via `sqlite3.sqlite_version`; inspect the linked target Windows runtime and its shipped notices. |
| `starlette` | `1.10.0` | BSD-3-Clause | Sandbox metadata; target resolution **VERIFY**. FastAPI's ASGI/web dependency. |
| `beautifulsoup4` | `4.15.0` | MIT License | Sandbox metadata; target resolution **VERIFY**. Stored-text HTML parsing and optional online page-text extraction. |
| `requests` | `2.34.2` | Apache-2.0 | Sandbox metadata; target resolution **VERIFY**. HTTP client for the manually invoked optional public-page collector only; not used for AI inference. |
| `pytest` | `8.4.2` | MIT | Sandbox metadata; target resolution **VERIFY**. Development/test dependency. |
| `setuptools` | `66.1.1` (below declared `>=68.0`) | MIT in the `License :: OSI Approved :: MIT License` classifier; no `License` field | Target build resolution/licence **VERIFY**. |
| `sentence-transformers` | Not installed; `3.4.1` was user-reported | Apache-2.0 was user-reported | No local package metadata; target version/licence **VERIFY**. Does not verify the embedding model licence above. |
| `huggingface-hub` | **VERIFY** — not installed in sandbox | **VERIFY** — no local metadata | Transitive embedding-runtime dependency; inspect actual target resolution. |
| `numpy` | **VERIFY** — not installed in sandbox | **VERIFY** — no local metadata | Transitive embedding-runtime dependency; inspect actual target resolution. |
| `transformers` | **VERIFY** — not installed in sandbox | **VERIFY** — no local metadata | Transitive embedding-runtime dependency; inspect actual target resolution. |
| `tokenizers` | **VERIFY** — not installed in sandbox | **VERIFY** — no local metadata | Transitive embedding-runtime dependency; inspect actual target resolution. |
| `torch` | **VERIFY** — not installed in sandbox | **VERIFY** — no local metadata | Transitive embedding-runtime dependency; inspect actual target resolution. |
| `scrapy` | Not installed or declared | Not applicable to current dependencies | Not used by this application. |
| `playwright` | Not installed or declared | Not applicable to current dependencies | Not used by this application. |

## Frontend npm distributions

The dashboard uses the locked frontend dependencies in `frontend/package-lock.json`.
Versions and licence identifiers below were rechecked from installed package
metadata under `frontend/node_modules`. The repository contains application,
framework, icon, and bundled-font notices under `frontend/static/licenses/`;
verify the exact notice set included in any deployed bundle.

| Distribution | Locked version | Observed licence | Role |
|---|---:|---|---|
| `react` | `19.3.1` | MIT in installed package metadata and checked-in licence notice; deployed bundle notice set **VERIFY** | Dashboard UI runtime. |
| `react-dom` | `19.3.1` | MIT in installed package metadata and checked-in licence notice; deployed bundle notice set **VERIFY** | Dashboard DOM renderer. |
| `lucide-react` | `0.468.0` | ISC | Dashboard icons. |
| `tailwindcss` | `4.3.5` | MIT | Dashboard stylesheet generation. |
| `@tailwindcss/vite` | `4.3.5` | MIT | Vite integration for Tailwind CSS. |
| `@vitejs/plugin-react` | `4.7.0` | MIT | React build and development tooling. |
| `vite` | `6.4.6` | MIT | Frontend build and development server. |
| `@fontsource-variable/inter` | `5.3.0` | OFL-1.1 | Bundled Inter variable font files. |
| `@fontsource-variable/jetbrains-mono` | `5.3.0` | OFL-1.1 | Bundled JetBrains Mono variable font files. |

The problem-statement workflow adds no package or model distribution; it uses
the existing local Ollama client and selected locally installed model. Package
licence fields are now recorded from installed sandbox metadata where available;
target Windows resolutions remain **VERIFY**. The Ollama distribution licence,
Qwen3 artifact terms, exact all-MiniLM-L6-v2 revision/card, linked target SQLite
runtime, and deployed frontend notice set also remain **VERIFY**. Exact official
pages for these checks are listed in
[`MODELS_AND_LICENCES.md`](MODELS_AND_LICENCES.md). The frontend versions above
are from this sandbox's locked install, not a Windows runtime verification.
This project is an AGPL-3.0-only derivative; retain `LICENSE` and `NOTICE` with
distributions.
