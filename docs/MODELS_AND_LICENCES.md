# Models, licenses, and repository lineage

**Status:** Phase 2 license gate is not complete. No embedding dependency has been added. The live Ollama smoke attempt was blocked because the sandbox has no Ollama process or executable; see `test_evidence/smoke_ollama.txt`.

## Current application tree

The rebuilt working tree is original MIT-licensed application code (`LICENSE`, `pyproject.toml`). The GitHub repository is a real fork: GitHub reports parent `ethanplusai/sellbird`; the upstream repository was named `ethanplusai/harvey` when v0.3.0 was released and now resolves to the renamed `sellbird` repository. The current tree was rebuilt rather than copied from the legacy implementation. It is informed by ideas such as deterministic scoring, a signal catalog, and anti-fabrication safeguards, but contains no copied legacy application code.

The checked-out pre-rebuild baseline was `b212385259da92246a56311d790d936e75dd70dd` (Sellbird 0.4.0, AGPL-3.0-only). The local annotated tag `legacy-sellbird` points to that commit. It retains the original historical tree, including AGPL-licensed code and provider references; the verify script checks the working tree, not Git history or tags. Historical inference ran through the Anthropic Claude Code CLI and OpenAI Codex CLI/app-server, and the old quota integration also referenced Claude's OAuth usage endpoint. Those names describe tagged history, not dependencies or behavior in the rebuilt tree.

**Tag decision:** keep `legacy-sellbird` locally for lineage, but do not push it during this review. Pushing the tag would publish the old AGPL tree and its historical provider references. The final merge to the default branch and `v1.0` tag are deferred until review and final acceptance.

The checkout is shallow/grafted at the baseline, so its local history cannot establish whether the MIT v0.3.0 commit is an ancestor of that baseline.

## Installed runtime dependency metadata

These licenses were read from `importlib.metadata` in the fresh project virtual environment on 2026-11-22:

| Distribution | Installed version | Metadata license |
|---|---:|---|
| FastAPI | 0.165.0 | MIT |
| HTTPX | 0.28.1 | BSD-3-Clause |
| Pydantic | 2.14.4 | MIT |
| psutil | 7.2.2 | BSD-3-Clause |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| pytest (development) | 8.4.2 | MIT |

SQLite is provided by Python's standard library. The dependency manifests list the same five runtime packages; `psutil` is the only newly approved foundation dependency.

## Embedding dependency and model — pending verification

The embedding dependency gate is **not satisfied**, so neither `sentence-transformers` nor PyTorch has been added to the project environment or manifests.

| Component | Verification status |
|---|---|
| `sentence-transformers` | Not installed; exact license from installed distribution metadata has not been verified. |
| `torch` (CPU-only) | Not installed. PyPI's standard Linux wheel metadata lists CUDA toolkit dependencies, so it is not an acceptable substitute for the requested CPU-only build; CPU wheels are served from PyTorch's separate wheel index, which is outside the sandbox's permitted package-download hosts. |
| `transformers`, `tokenizers`, `huggingface-hub`, and other runtime dependencies | Not installed for a license audit; their exact installed metadata licenses remain to be collected together with the approved CPU-only version set. |
| `sentence-transformers/all-MiniLM-L6-v2` | **Apache-2.0**, verified in the official card's metadata at [`README.md` on Hugging Face](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/raw/main/README.md) (`license: apache-2.0`, checked 2026-11-22). |

The dependency gate remains open. Before adding the embedding stack, install the intended CPU-only versions in an isolated environment and record each exact `License`/`License-Expression` from installed distribution metadata (including PyTorch, Transformers, Tokenizers, Hugging Face Hub, NumPy, SciPy, scikit-learn, and other runtime transitive dependencies). PyPI metadata for `torch` does not provide the requested CPU-only wheel: its Linux wheels declare CUDA dependencies; the CPU wheel index is outside this sandbox's permitted package-download hosts. Until an isolated CPU-only install and full metadata audit are possible, the model fetcher, embedder, and network-disabled inference test remain blocked.
