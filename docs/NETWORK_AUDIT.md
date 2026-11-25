# Outbound network and AI-path audit

## Source inventory

| Source / client | Activity | AI path? | Destination / control |
|---|---|---:|---|
| `app/llm_client.py` (`httpx.Client`) | Ollama health/version probes and model inference | Yes | The `OLLAMA_URL` constant is `http://127.0.0.1:11434`; there is no environment/config override and the HTTPX client sets `trust_env=False`. |
| `app/embeddings.py` (`SentenceTransformer`) | Loads the local sentence-transformer model and encodes product/page text for ranking | Yes | The loader forces `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before import/load. With `OFFLINE_STRICT=1`, Hub telemetry and implicit-token use are disabled too. Cache model files in advance; no hosted inference endpoint is used. |
| `frontend/index.html` (`fetch`) | Dashboard calls the Harvey API | No direct model call | All URLs are relative `/api/...` paths and therefore use the service's same origin. AI requests are delegated to the backend above. |
| `scripts/fetch_public_pages.py` (`requests.Session`) | Optional, manual fetch of URLs supplied in CSV; checks per-origin `robots.txt`, follows only validated public redirects, and saves extracted text under `data/prospect_pages/` | No | Requires an explicit online invocation. Standard ports only; rejects non-global IP destinations; bounds redirects, bytes, timeout, and per-origin request rate. It does not import `app.llm_client`. |
| Other `app/**/*.py` source in the audited checkout | Static scan for URLs, cloud SDK imports, and common HTTP client imports/calls | No outbound client found | No other explicit external client or non-local URL was found in application source. |

All server-side model calls use the single HTTPX path in `app/llm_client.py`.
There is no cloud SDK, hosted model fallback, or paid AI service in the app
source inventory. The FastAPI application reads locally stored prospect-page
text only; fresh public-page collection is an opt-in script outside the API
and AI workflow. A source-level test asserts that this helper does not import
`app.llm_client`.

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
- `make offline` sets `OFFLINE_STRICT=1` plus both Hugging Face/Transformers
  offline flags and runs the deterministic verification suite. It is not proof
  that Wi-Fi was disabled;
  the target-machine offline acceptance and network-isolation checks remain
  operator-run and are not claimed here.

## Evidence and limits

- `tests/test_llm_client.py` mocks HTTPX and asserts the base URL remains
  loopback even when `OLLAMA_URL`/`OLLAMA_HOST` environment variables contain
  non-local values. `tests/test_ai_network_boundary.py` scans app source for
  cloud SDK imports, non-local URLs, and HTTP clients without a fixed loopback
  destination. `make verify` also runs `scripts/verify_no_cloud.py`.
- No-cloud coverage includes `tests/test_smoke.py::test_verify_script_exists_and_mentions_local_only` and `tests/test_ai_network_boundary.py::test_ai_path_has_no_cloud_sdk_imports_or_nonlocal_urls`; `make verify` also runs `scripts/verify_no_cloud.py`.
- `tests/test_embeddings.py::test_model_load_forces_hugging_face_and_transformers_offline` and `tests/test_embeddings.py::test_offline_strict_forces_cache_only_model_loading_and_disables_telemetry` mock the sentence-transformer loader and verify offline flags are set before the model constructor runs.
- Hardware behavior is covered by `tests/test_hardware.py::test_tiering_from_fake_ram_and_vram_values`, `test_context_budget_is_keyed_to_hardware_tier`, `test_detect_caches_hardware_for_process_lifetime`, and `test_hardware_endpoint_reports_detected_fields`.
- `scripts/offline_acceptance.ps1` records the configured Ollama host and
  checks established peers belonging to the API process. This live check is
  intentionally left for the user; the script has not been run here.
- Static source scans and mocked tests do not prove the behavior of every
  transitive library or of a target machine's network stack. The separate
  user-run internet-off acceptance test has not been run. No such external
  network test was performed in this audit.
