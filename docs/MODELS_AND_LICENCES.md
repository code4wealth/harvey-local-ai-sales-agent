# Models and dependency licences

The observed versions and licence metadata are recorded in
[`LICENSES.md`](LICENSES.md). Unverified values are explicitly marked
**VERIFY**; user-reported or intended licences are not presented as independently
verified metadata.

## Local models

- Text generation uses the `qwen3:4b` Ollama tag by default when configured.
  The installed Ollama version, local model list, model-card licence metadata,
  and live model availability were not run in the audit sandbox. See
  `LICENSES.md` for the observation and limitations.
- Embeddings use `sentence-transformers/all-MiniLM-L6-v2`; its model revision
  and model-card licence are **VERIFY** in `LICENSES.md`. Model files must be
  cached before use. The application sets `HF_HUB_OFFLINE=1` and
  `TRANSFORMERS_OFFLINE=1` before the model loader runs; `OFFLINE_STRICT=1`
  additionally disables Hub telemetry and implicit-token use. It does not
  download model files or use a hosted inference endpoint.

All model inference is directed to the hard-coded loopback Ollama URL in
`app/llm_client.py`. Harvey's AGPL-3.0-only notice and upstream attribution
remain in `LICENSE` and `NOTICE`.
