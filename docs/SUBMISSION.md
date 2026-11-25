# Submission notes

## Repository and demo identity

- Repository: [code4wealth/harvey-local-ai-sales-agent](https://github.com/code4wealth/harvey-local-ai-sales-agent) — `gh repo view` currently reports it as a public fork. Recheck access after the branch is pushed.
- Working branch: `arena/235805fd-harvey-local-ai-sales-agent`
- Demo footer commit hash: **PENDING** — the owner-provided field was left as `[HASH]`; do not substitute the current local `HEAD` without checking the recording.
- Demo video URL: **PENDING** — no URL was supplied. The prompt's `[PASTE LINK or "not yet uploaded"]` is an unresolved choice, not a confirmed upload status.
- Demo screen: `/operations` (the product-level workflow console). The eight individual PowerShell acceptance workflows are a separate run, not a ninth `/operations` step.

The working branch has not been pushed by this completion pass. Publish it before asking reviewers to fetch this branch or compare the demo footer.

## Demo version

The demo video was recorded on the owner's Windows laptop at commit [VIDEO_COMMIT_HASH]. Later commits (e171ea8, 943d12b and any after) add model-readiness checks, honest UI status labels and documentation; they do not change the evidence validators or the local-only inference path.

- Video commit hash: `[VIDEO_COMMIT_HASH]` — **OWNER TO FILL** (read from the footer of the video).
- Video URL: `[VIDEO_URL]` — **OWNER TO FILL**.
- CI result (Python 3.11 and 3.12): `[CI_RESULT_PYTHON_3_11_AND_3_12]` — **OWNER TO FILL**.

## Owner-reported target-laptop runs

Windows runs: owner-reported, 2026-11-26 (local time, IST). The workspace snapshot carries earlier timestamps (2026-11-23 UTC); the runs were performed afterwards. The date field is owner-confirmed; the results are not backed by target-laptop captures here.

- Local inference used Ollama with `qwen3:4b`. The owner reports `ollama ps` showed about **66% GPU / 34% CPU** on an RTX 3050, with 15.7 GB RAM and 12 CPUs. The current Ollama version, exact model digest, and embedding-device placement were not supplied.
- Online FieldNest workflow: profile, ICP, signals, problem statement, draft, and ranking reportedly completed; 20 prospects and 60 sample replies were imported. The owner reports `R004` classified as `not_interested`, matching the ambiguous development label in `data/eval/reply_labels.csv`. That file verifies the label, not the live inference result.
- Offline workflow: the owner reports all eight workflows worked with Wi-Fi disconnected and that the run was screen-recorded. The exact script, run logs, ping result, and port-11434 `netstat` capture were not supplied.
- Ollama outage/recovery result, screenshots, demo-video URL, and demo footer commit hash remain **PENDING** because the fields were left as unresolved alternatives/placeholders.

### Evidence files present in this checkout

The only files currently present under `test_evidence/` are:

- `test_evidence/online/README.md` — owner-reported summary plus capture template; not primary run evidence or a screenshot.
- `test_evidence/real_run/smoke_embeddings.txt` — earlier operator-provided embedding smoke record.
- `test_evidence/real_run/smoke_ollama.txt` — earlier single-call Ollama smoke record.

There are no files under `test_evidence/offline/` or `test_evidence/ollama_outage/`, and no screenshot image is present under `test_evidence/` in this checkout. The repository has three static UI screenshots under `docs/images/` (`dashboard.png`, `dashboard-selected.png`, `dashboard-mobile.png`); they are not evidence from the owner-reported run. The owner's screen recording is not stored here. Do not invent evidence filenames or describe missing files as attached.

## Run locally in six steps

1. Install Python 3.11+, Git, GNU Make, and Ollama. Clone the repository. To obtain the submission branch, publish it first, then run:
   ```bash
   git clone --branch arena/235805fd-harvey-local-ai-sales-agent https://github.com/code4wealth/harvey-local-ai-sales-agent.git
   cd harvey-local-ai-sales-agent
   ```
2. Create and activate a virtual environment, then install the project and test tools:
   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'
   ```
   On Windows PowerShell, activate with `\.venv\Scripts\Activate.ps1` or invoke `\.venv\Scripts\python.exe` directly; do not change the machine-wide execution policy.
3. Check the source boundary and tests:
   ```bash
   python scripts/verify_no_cloud.py
   pytest -q
   ```
   These checks use mocked Ollama responses and fake embeddings; they are not a live-model or offline-network test.
4. Start local Ollama and pull the intended local model, for example `ollama pull qwen3:4b`. While online, cache `sentence-transformers/all-MiniLM-L6-v2` directly before setting offline flags:
   ```bash
   python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")'
   ```
   Verify the selected model tag exists with `ollama list`; model and package licence review remains separate.
5. Set `DEFAULT_MODEL=qwen3:4b` and `DB_PATH=data/harvey.db`; after model caching, set `OFFLINE_STRICT=1` if desired. Start the API bound to loopback only:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
   In PowerShell, set these values with `$env:DEFAULT_MODEL`, `$env:DB_PATH`, and `$env:OFFLINE_STRICT` in the API process's shell.
6. Open `http://127.0.0.1:8000/operations`. Create/select a product and import only fictional `SAMPLE` records from the repository. For offline acceptance, cache the models first, disconnect Wi-Fi, then run `scripts/offline_acceptance.ps1`; run `scripts/ollama_down_check.ps1` separately for controlled outage/recovery. Follow [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) and preserve actual logs/JSON. The script's `example.com` probe alone does not prove full network isolation.

The dashboard at `/` includes illustrative browser-preview data, explicitly marked `PREVIEW`; it is not the SQLite workspace. The **Simulate offline** control is a UI-only demonstration and does not turn off Wi-Fi or stop the Ollama process. `SAMPLE` products, prospects, page text, and reply records are fictional. No prospect discovery, hosted AI, or email-send integration is performed.

## Cost statement

**Inference/API cost: $0; no API keys are required.** Model inference is local through Ollama. Local hardware, electricity, and one-time model-download bandwidth are user-provided and are not priced here. The optional explicit-URL page collector is an online non-AI helper, separate from inference.

## Known limitations and evidence boundary

- Owner-reported Windows results are not backed by run logs, screenshots, or a video file in this checkout. Windows runs: owner-reported, 2026-11-26 (local time, IST). The workspace snapshot carries earlier timestamps (2026-11-23 UTC); the runs were performed afterwards. The run outcomes remain unverified here.
- Offline workflow completion is owner-reported; the exact PowerShell script run, `example.com` result, ping result, `netstat` listener observation, and packet/network capture remain unverified here.
- The Ollama outage/recovery outcome, demo URL, screenshot list, and demo footer commit hash were not supplied.
- Automated tests use mocked Ollama responses and fake embeddings. They do not prove Windows behavior, full outbound-traffic isolation, live model quality, CPU/GPU placement, or outage recovery.
- The optional explicit-URL page collector requires internet access. It is not used by local inference, but the product is not an all-network-activity-off application while that helper is run.
- Model weights and target Windows package licences/resolutions remain **VERIFY**. See the official-page checklist below and [`MODELS_AND_LICENCES.md`](MODELS_AND_LICENCES.md).

## Outstanding licence checks — official pages to inspect

No licence values below are asserted as verified by this submission. Check the exact artifact/tag/revision or installed Windows package set and preserve the actual version/digest and notices. The complete inventory and per-package links are in [`MODELS_AND_LICENCES.md`](MODELS_AND_LICENCES.md).

| Remaining **VERIFY** | Official page(s) to check |
|---|---|
| Qwen3 Ollama artifact(s): current `qwen3:4b`, any configured override, and the other recommended tags (`qwen3:1.7b`, `qwen3:8b`, `qwen3:14b`) if used. Match the exact local Ollama manifest/digest; family cards alone do not identify the packaged artifact. | [Ollama Qwen3 library/tags](https://ollama.com/library/qwen3); source model cards: [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B), [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B), [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), [Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B). |
| `sentence-transformers/all-MiniLM-L6-v2` exact downloaded revision and model-card terms (separate from the Python distribution). | [Hugging Face model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). |
| `sentence-transformers` Python distribution and actual Windows embedding dependency resolution. | [sentence-transformers on PyPI](https://pypi.org/project/sentence-transformers/); then inspect each installed distribution's metadata on Windows. |
| Ollama Windows distribution/version and shipped notices. | [Ollama releases](https://github.com/ollama/ollama/releases) and [Ollama source licence](https://github.com/ollama/ollama/blob/main/LICENSE). |
| Linked SQLite runtime in the target Windows Python build and applicable notices. | [SQLite copyright/licensing](https://sqlite.org/copyright.html) and [Python `sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html). |
| Windows-resolved direct runtime/test/build packages: `fastapi`, `uvicorn`, `httpx`, `pydantic`, `sentence-transformers`, `beautifulsoup4`, `requests`, `pytest`, `setuptools`. | Official PyPI pages: [fastapi](https://pypi.org/project/fastapi/), [uvicorn](https://pypi.org/project/uvicorn/), [httpx](https://pypi.org/project/httpx/), [pydantic](https://pypi.org/project/pydantic/), [sentence-transformers](https://pypi.org/project/sentence-transformers/), [beautifulsoup4](https://pypi.org/project/beautifulsoup4/), [requests](https://pypi.org/project/requests/), [pytest](https://pypi.org/project/pytest/), [setuptools](https://pypi.org/project/setuptools/). |
| Windows-resolved framework/test transitives: `starlette`, `anyio`, `annotated-doc`, `opentelemetry-api`, `typing-inspection`, `pydantic-core`, `annotated-types`, `typing-extensions`, `httpcore`, `certifi`, `idna`, `click`, `h11`, `soupsieve`, `packaging`, `iniconfig`, `pluggy`, `Pygments`. | Official PyPI pages: [starlette](https://pypi.org/project/starlette/), [anyio](https://pypi.org/project/anyio/), [annotated-doc](https://pypi.org/project/annotated-doc/), [opentelemetry-api](https://pypi.org/project/opentelemetry-api/), [typing-inspection](https://pypi.org/project/typing-inspection/), [pydantic-core](https://pypi.org/project/pydantic-core/), [annotated-types](https://pypi.org/project/annotated-types/), [typing-extensions](https://pypi.org/project/typing-extensions/), [httpcore](https://pypi.org/project/httpcore/), [certifi](https://pypi.org/project/certifi/), [idna](https://pypi.org/project/idna/), [click](https://pypi.org/project/click/), [h11](https://pypi.org/project/h11/), [soupsieve](https://pypi.org/project/soupsieve/), [packaging](https://pypi.org/project/packaging/), [iniconfig](https://pypi.org/project/iniconfig/), [pluggy](https://pypi.org/project/pluggy/), [Pygments](https://pypi.org/project/Pygments/). |
| Windows-resolved embedding-stack packages, depending on actual extras/platform: `transformers`, `huggingface-hub`, `torch`, `tokenizers`, `numpy`, `scipy`, `scikit-learn`, `Pillow`, `safetensors`, `tqdm`, `filelock`, `fsspec`, `regex`, `PyYAML`. | Official PyPI pages: [transformers](https://pypi.org/project/transformers/), [huggingface-hub](https://pypi.org/project/huggingface-hub/), [torch](https://pypi.org/project/torch/), [tokenizers](https://pypi.org/project/tokenizers/), [numpy](https://pypi.org/project/numpy/), [scipy](https://pypi.org/project/scipy/), [scikit-learn](https://pypi.org/project/scikit-learn/), [Pillow](https://pypi.org/project/Pillow/), [safetensors](https://pypi.org/project/safetensors/), [tqdm](https://pypi.org/project/tqdm/), [filelock](https://pypi.org/project/filelock/), [fsspec](https://pypi.org/project/fsspec/), [regex](https://pypi.org/project/regex/), [PyYAML](https://pypi.org/project/PyYAML/). |
| PowerShell/.NET acceptance tooling and optional NVIDIA driver/tool notices. | [PowerShell licence](https://github.com/PowerShell/PowerShell/blob/master/LICENSE.txt), [.NET runtime licence](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT), and [NVIDIA driver downloads](https://www.nvidia.com/Download/index.aspx). |
| Deployed React notice set. | [React on npm](https://www.npmjs.com/package/react) and [React DOM on npm](https://www.npmjs.com/package/react-dom); inspect the bundle's actual included notices. |

The exact official package pages in `MODELS_AND_LICENCES.md` are review pointers, not proof of the target versions or licence conclusions. Do not mark any remaining **VERIFY** complete until the actual Windows install/artifact is checked.

## Lineage

Fork of ethanplusai/harvey (now Sellbird). The hosted-AI implementation was removed and rebuilt on local Ollama, SQLite and Sentence Transformers, keeping the upstream's design ideas and attribution. See NOTICE for lineage and licence history.
