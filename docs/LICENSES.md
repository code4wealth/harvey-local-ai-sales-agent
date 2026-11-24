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
| `beautifulsoup4` | `4.15.0` | MIT License | Sandbox metadata; target resolution **VERIFY**. Stored-text HTML parsing. |
| `pytest` | `8.4.2` | MIT | Sandbox metadata; target resolution **VERIFY**. Development/test dependency. |
| `sentence-transformers` | `3.4.1` (user-reported `pip show`) | Apache 2.0 (user-reported `pip show`) | Package metadata is user-reported; installed target version **VERIFY**. Does not verify the embedding model licence above. |
| `huggingface-hub` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `numpy` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `transformers` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `tokenizers` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `torch` | **VERIFY** — not inspected | **VERIFY** — no local package metadata | Transitive embedding-runtime dependency; inspect after installing the target environment. |
| `scrapy` | Not installed or declared | Not applicable to current dependencies | Not used by this application. |
| `playwright` | Not installed or declared | Not applicable to current dependencies | Not used by this application. |

The problem-statement workflow adds no package or model distribution; it uses
the existing local Ollama client and selected locally installed model. Exact
resolved dependency versions and licences on the target machine, the Ollama
distribution licence, Qwen3's model licence, and the all-MiniLM-L6-v2 model-card
licence remain **VERIFY** items. This project is an AGPL-3.0-only derivative;
retain `LICENSE` and `NOTICE` with distributions.
