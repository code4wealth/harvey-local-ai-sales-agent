# Licence and version inventory

This table separates repository/package metadata and user-reported observations
from licence facts not verified in this environment. Every outstanding check is
marked **VERIFY**; a Python distribution's licence is not the licence of its
separately downloaded model weights. No files were present under
`test_evidence/offline/` for this update, and Ollama/PowerShell were not
available for a fresh local inspection.

## Models and runtime

| Component | Version / identifier | Licence | Verification status / role |
|---|---|---|---|
| Harvey Local AI Sales Agent | `0.1.0` (`pyproject.toml`) | `AGPL-3.0-only` | Verified from repository `LICENSE` and `NOTICE`; application. |
| Ollama | `0.40.17` (user-reported `ollama --version`) | **VERIFY** | Distribution licence was not supplied or independently inspected; local model server. |
| Qwen3 | `qwen3:4b`; ID `359d7dd4bcda`; 2.5 GB (user-reported `ollama list`) | **VERIFY** — Apache License 2.0 was reported from `ollama show`, not independently inspected here | Local text-generation model; tag and licence remain user-reported. |
| `sentence-transformers/all-MiniLM-L6-v2` | Model revision **VERIFY** | **VERIFY** — model-card licence was not inspected | Local embedding model; files must be cached before use. This model licence is separate from the Python `sentence-transformers` package licence. |

## Python distributions

The following versions and licence identifiers are environment metadata reported
from the repository sandbox (`License-Expression` where present, otherwise
`License`); they do not establish the exact versions resolved on the target
Windows machine. Target resolution/licence checks remain **VERIFY**.

| Distribution | Observed version | Observed licence metadata | Verification status / role |
|---|---:|---|---|
| `fastapi` | `0.165.0` | MIT | Sandbox metadata; target resolution **VERIFY**. API framework. |
| `uvicorn` | `0.54.0` | BSD-3-Clause | Sandbox metadata; target resolution **VERIFY**. ASGI server. |
| `httpx` | `0.28.1` | BSD-3-Clause | Sandbox metadata; target resolution **VERIFY**. Fixed loopback Ollama transport. |
| `pydantic` | `2.14.4` | MIT | Sandbox metadata; target resolution **VERIFY**. Structured request/response validation. |
| `starlette` | `1.10.0` | BSD-3-Clause | Sandbox metadata; target resolution **VERIFY**. FastAPI's ASGI/web dependency. |
| `beautifulsoup4` | `4.15.0` | MIT License | Sandbox metadata; target resolution **VERIFY**. Stored-text HTML parsing and optional online page-text extraction. |
| `requests` | `2.34.2` | Apache-2.0 | Sandbox metadata; target resolution **VERIFY**. HTTP client for the manually invoked optional public-page collector only; not used for AI inference. |
| `pytest` | `8.4.2` | MIT | Sandbox metadata; target resolution **VERIFY**. Development/test dependency. |
| `sentence-transformers` | `3.4.1` (user-reported `pip show`) | Apache 2.0 (user-reported `pip show`) | Package metadata is user-reported; installed target version **VERIFY**. Does not verify the embedding model licence above. |
| `huggingface-hub` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `numpy` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `transformers` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `tokenizers` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `torch` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `scrapy` | Not installed or declared | Not applicable to current dependencies | Not used by this application. |
| `playwright` | Not installed or declared | Not applicable to current dependencies | Not used by this application. |

## Frontend npm distributions

The dashboard uses the locked frontend dependencies in `frontend/package-lock.json`.
Versions and SPDX licence identifiers below were read from the installed package
metadata during the local production build. The build copies the application,
framework, icon, and bundled-font notices into `frontend/static/licenses/`.

| Distribution | Locked version | Observed licence | Role |
|---|---:|---|---|
| `react` | `19.3.1` | MIT | Dashboard UI runtime. |
| `react-dom` | `19.3.1` | MIT | Dashboard DOM renderer. |
| `lucide-react` | `0.468.0` | ISC | Dashboard icons. |
| `tailwindcss` | `4.3.5` | MIT | Dashboard stylesheet generation. |
| `@tailwindcss/vite` | `4.3.5` | MIT | Vite integration for Tailwind CSS. |
| `@vitejs/plugin-react` | `4.7.0` | MIT | React build and development tooling. |
| `vite` | `6.4.6` | MIT | Frontend build and development server. |
| `@fontsource-variable/inter` | `5.3.0` | OFL-1.1 | Bundled Inter variable font files. |
| `@fontsource-variable/jetbrains-mono` | `5.3.0` | OFL-1.1 | Bundled JetBrains Mono variable font files. |

The problem-statement workflow adds no package or model distribution; it uses
the existing local Ollama client and selected locally installed model. Exact
resolved Python dependency versions and licences on the target machine, the
Ollama distribution licence, Qwen3's model licence, and the
all-MiniLM-L6-v2 model-card licence remain **VERIFY** items. The frontend
versions above are from this sandbox's locked install and are not a Windows
runtime verification. This project is an AGPL-3.0-only derivative; retain
`LICENSE` and `NOTICE` with distributions.
