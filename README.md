# Harvey Local Multi-Product AI Sales Agent

A local-first foundation for product-specific sales research and drafting. Every model call is routed through `app/llm_client.py` to Ollama at the fixed address `http://127.0.0.1:11434`; the client has no remote endpoint configuration or fallback.

## Upstream and rebuild status

GitHub identifies this repository as a real fork of `ethanplusai/sellbird`; the upstream repository was named `ethanplusai/harvey` when its v0.3.0 MIT release was published and has since been renamed. The current working tree was rebuilt from scratch for the local-first assignment. It carries forward only design ideas—such as deterministic scoring concepts, the signal catalog, and anti-fabrication safeguards—not legacy implementation code.

See [`docs/MODELS_AND_LICENCES.md`](docs/MODELS_AND_LICENCES.md) for the license and history notes. The historical `legacy-sellbird` tag is kept locally for lineage and is not pushed during this review phase.

## Current implementation

The current foundation includes:

- A synchronous local inference client with structured JSON validation, up to two retries for invalid output, Qwen-style response cleaning, and inference logging for token counts, request latency, and generation throughput when Ollama reports it.
- Hardware detection and deterministic local-model recommendations.
- A SQLite foundation for products, a retryable AI task queue, and inference logs.
- A queue worker that retries tasks after the local inference service returns.
- A live `qwen3:4b` smoke script. Its latest run is **BLOCKED** because Ollama is not running in the sandbox; no live model result is claimed. See `test_evidence/smoke_ollama.txt`.
- Fictional `SAMPLE` data: two products, 25 prospects with page texts, and 20 labelled replies (13 development, 7 held out). No classifier accuracy is claimed because classification and its evaluator are not implemented yet.
- Unit tests using HTTPX's in-process mock transport; no running model or network is needed for those unit tests.

The API, dashboard, product workflows, embeddings, and end-to-end offline acceptance run remain future work. Embeddings are gated on a full installed-metadata license audit and a usable CPU-only PyTorch installation; see [`docs/MODELS_AND_LICENCES.md`](docs/MODELS_AND_LICENCES.md) and [`docs/TASKS.md`](docs/TASKS.md). This foundation does not send email, perform paid research, or ship trainer defaults.

## Setup

Use Python 3.11 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

For local inference, install Ollama separately, then start it and pull a model in another terminal:

```sh
ollama serve
ollama pull qwen3:4b
```

The default model is selected from detected hardware when `DEFAULT_MODEL` is blank. You can set `DEFAULT_MODEL` to a model already installed in your local Ollama instance. `DB_PATH` can point to a local SQLite file; by default the database is `./data/harvey.db`. No API keys are used or needed. `.env.example` lists the local settings; the client always uses the fixed local endpoint regardless of environment variables.

## Development and verification

```sh
make verify
```

The verifier scans source/configuration for prohibited hosted inference references and checks that the inference client uses only the local endpoint; pytest then runs the suite. Current tests use mock HTTP responses and temporary SQLite files.

The client can be used directly:

```python
from app.llm_client import OllamaClient, OllamaUnavailable

with OllamaClient() as client:
    try:
        text = client.generate_or_queue(
            task="profile",
            prompt="Use only the product facts supplied here.",
        )
    except OllamaUnavailable as error:
        # Show the clear message and retain error.task_id for queue status.
        print(error, error.task_id)
```

The `QueueWorker` can drain persisted tasks once the local server is available. Deterministic operations do not require Ollama.

## Project rules

- Keep all model inference inside `app/llm_client.py` and only on `127.0.0.1:11434`.
- Never add a hosted inference dependency or silent fallback.
- Label test fixtures and sample data `SAMPLE`; never describe mocked output as real intelligence.
- Do not add email sending, paid research, CRM integrations, or trainer default values.
- Ask before adding dependencies. `psutil` (BSD-3-Clause) is the only newly approved foundation dependency; embedding dependencies are deferred pending a license review.

## License

The newly authored application code is MIT licensed. The old Sellbird 0.4.0 baseline is preserved separately by the `legacy-sellbird` tag; see `NOTICE` for the lineage note.
