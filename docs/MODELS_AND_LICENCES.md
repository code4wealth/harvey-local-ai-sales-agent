# Models and dependency licences

The exact versions and locally available licence metadata observed in the
current sandbox are recorded in [`LICENSES.md`](LICENSES.md). Values that could
not be inspected there are explicitly marked `not run`; intended licences are
not presented as verified metadata.

## Local models

- Text generation uses the `qwen3:4b` Ollama tag by default when configured.
  The installed Ollama version, local model list, model-card licence metadata,
  and live model availability were not run in the audit sandbox. See
  `LICENSES.md` for the observation and limitations.
- Embeddings use `sentence-transformers/all-MiniLM-L6-v2`. Model files must be
  cached before use. The application sets `HF_HUB_OFFLINE=1` and
  `TRANSFORMERS_OFFLINE=1` before the model loader runs; it does not download
  them or use a hosted inference endpoint.

All model inference is directed to the hard-coded loopback Ollama URL in
`app/llm_client.py`. Harvey's AGPL-3.0-only notice and upstream attribution
remain in `LICENSE` and `NOTICE`.
