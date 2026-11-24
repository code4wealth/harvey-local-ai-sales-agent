# Outbound network and AI-path audit

## Source inventory

| Source / client | Activity | AI path? | Destination / control |
|---|---|---:|---|
| `app/llm_client.py` (`httpx.Client`) | Ollama health/version probes and model inference | Yes | The `OLLAMA_URL` constant is `http://127.0.0.1:11434`; there is no environment/config override and the HTTPX client sets `trust_env=False`. |
| `app/embeddings.py` (`SentenceTransformer`) | Loads the local sentence-transformer model and encodes product/page text for deterministic ranking | Yes | The loader forces `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before importing/loading the model. Model files must be cached in advance; no hosted inference endpoint is used. |
| `frontend/index.html` (`fetch`) | Dashboard calls the Harvey API | No direct model call | All URLs are relative `/api/...` paths and therefore use the service's same origin. AI requests are delegated to the backend above. |
| Other `app/**/*.py` source in the audited checkout | Static scan for URLs, cloud SDK imports, and common HTTP client imports/calls | No outbound client found | No other explicit external client or non-local URL was found by the audit scan. |

All server-side model calls use the single HTTPX path in `app/llm_client.py`.
There is no cloud SDK, hosted model fallback, or paid AI service in the app
source inventory. Product page text is stored locally and is not fetched by an
external research client in this checkout.

## Local-service security controls

- The documented and `make run` bind address is `127.0.0.1`. This API has no
  user authentication and must not be exposed on `0.0.0.0` or a LAN interface.
- A Host allowlist accepts loopback names and the Arena preview domain; other
  Host headers are rejected. State-changing browser requests
  carrying a mismatched `Origin`, or `Sec-Fetch-Site: cross-site`, receive 403.
  Non-browser local clients without those headers remain supported.
- API-configured company-info paths must be repository-relative and resolve
  inside `data/company_info/`; traversal, URLs, absolute paths, and symlinks
  escaping the directory are rejected. The profile reader applies the same
  containment check and caps source documents at 5 MiB.
- Prospect CSV uploads are capped at 5 MiB and local prospect-page text at
  1 MiB. These checks run while streaming request bodies, not only after a full
  in-memory read.
- `make offline` sets both Hugging Face/Transformers offline flags and runs the
  deterministic verification suite. It is not proof that Wi-Fi was disabled;
  the target-machine offline acceptance and network-isolation checks remain
  operator-run and are not claimed here.

## Evidence and limits

- `tests/test_llm_client.py` mocks HTTPX and asserts the base URL remains
  loopback even when `OLLAMA_URL`/`OLLAMA_HOST` environment variables contain
  non-local values. `tests/test_ai_network_boundary.py` scans app source for
  cloud SDK imports, non-local URLs, and HTTP clients without a fixed loopback
  destination. `make verify` also runs `scripts/verify_no_cloud.py`.
- `tests/test_embeddings.py` mocks the sentence-transformer loader and verifies
  both offline-mode variables are set before the model constructor runs.
- `scripts/offline_acceptance.ps1` records the configured Ollama host and
  checks established peers belonging to the API process. This live check is
  intentionally left for the user; the script has not been run here.
- Static source scans and mocked tests do not prove the behavior of every
  transitive library or of a target machine's network stack. The separate
  user-run internet-off acceptance test has not been run. No such external
  network test was performed in this audit.
