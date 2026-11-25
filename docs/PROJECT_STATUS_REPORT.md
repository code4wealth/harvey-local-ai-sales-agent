# Project Status Report

| Snapshot date | 2026-11-23 (UTC) |
|---|---|
| Repository | `code4wealth/harvey-local-ai-sales-agent` |
| Working branch | `arena/235805fd-harvey-local-ai-sales-agent` |
| Status | Core implementation and sandbox verification are present; target-machine artifact review, outage/demo evidence, and release checks remain incomplete. |

Windows runs: owner-reported, 2026-11-26 (local time, IST). The workspace snapshot carries earlier timestamps (2026-11-23 UTC); the runs were performed afterwards. Owner-reported results are kept separate from evidence verified here; no target-run logs or captures are present.

## Progress scorecards — different scopes

| Checklist | Checked | Remaining | Checked share | Scope |
|---|---:|---:|---:|---|
| [`TASKS.md`](TASKS.md) | 43 / 48 | 5 | **89.6%** | Build-plan and implementation tasks. |
| [`ACCEPTANCE_CHECKLIST.md`](ACCEPTANCE_CHECKLIST.md) | 21 / 34 | 13 | **61.8%** | Automated checks plus owner-reported workflow results and target-machine evidence/release gates. |

The lists have different denominators and purposes. **Do not combine them or present either as a universal project-completion percentage.** The acceptance checklist now marks the owner-reported eight-workflow result at the individual-workflow level, while retaining pending items for absent logs, unconfirmed acceptance-script execution, network evidence, unsent-state evidence, and broader checks.

## Implemented and checked in this workspace

- **Local inference boundary:** all inference goes through `app/llm_client.py` to the fixed Ollama endpoint `127.0.0.1:11434`; no cloud fallback is configured. The source guard and tests check this design. They are not a packet capture. An explicitly invoked public-page collector is an optional online, non-AI helper; inference workflows consume locally stored page text.
- **Workflow implementation:** product-scoped profile and ICP generation, prospect import/research, signals, evidence-grounded problem statements and unsent drafts, deterministic ranking, reply classification/evaluation, and a persistent product pipeline. The `/operations` console is distinct from the eight individual acceptance-script checks.
- **Evidence/data safeguards:** draft and problem-statement validators remain strict. The current prompt example is a deterministic non-evidence placeholder; a regression test confirms that placeholder cannot pass the existing draft evidence validator. Reply labels remain isolated from model inputs.
- **Model readiness and UI status:** Ollama model tags are checked before `/api/chat`; a missing tag reports local `ollama pull` guidance, and an Ollama/tag outage does not trigger a cloud fallback. `/api/status` reports installed tags, the resolved preference, failure reasons, and embedding-cache readiness. The browser no longer chooses a model. Preview records are marked separately from SQLite-backed rows. “Simulate offline” is explicitly a UI-only state and is labeled “Demo offline (simulated)” rather than as a real network outage.
- **Frontend:** the production bundle builds and is served with the local API. The workflow screen for a demonstration is `/operations`.

## Automated verification

- `python scripts/verify_no_cloud.py` — **passed**.
- `pytest -q` — **250 passed, 2 skipped**. The skipped tests are PowerShell parser checks because PowerShell is unavailable in this environment. The tests use mocked Ollama responses and fake embeddings; they do not prove live model behavior.
- `npm run build` — **passed** with Vite 6.4.6 after frontend changes.
- `git diff --check` — **passed** for tracked changes; the new status/submission documents were also checked for trailing whitespace.
- Regression coverage includes `/api/tags` model discovery, installed-model resolution, refusal to call `/api/chat` when tags are unavailable/missing, useful status/error text, preview separation, and explicit simulated-offline UI labels.

The repository also contains earlier operator-provided single-call Ollama and embedding smoke files. Those are narrow smoke records, not this full pipeline or a complete network-isolation result.

## Owner-reported Windows results — not independently verified here

- The owner reports local inference with `qwen3:4b` via Ollama and `ollama ps` placement of about **66% GPU / 34% CPU** on an RTX 3050, with **15.7 GB RAM** and **12 CPUs**. The current Ollama version, exact model digest, and embedding-device placement were not supplied.
- The owner reports an online FieldNest run completed profile, ICP, signals, problem statement, draft, and ranking; **20 prospects** and **60 sample replies** were imported. The owner reports `R004` classified `not_interested`. The checked-in evaluator data confirms that `R004` has the ambiguous development label; it does not independently confirm the runtime result or establish an accuracy metric.
- The owner reports that all eight workflows worked with Wi-Fi disconnected and that the run was screen-recorded. The exact script invocation, recording path, timestamped logs/JSON, ping result, and port-11434 `netstat` capture were not supplied.
- The Ollama outage/recovery status, screenshot list, and commit hash shown in the video footer remain **PENDING**. The owner supplied two Drive links, but their roles and contents are unconfirmed, so the demo video URL remains unresolved.

### Evidence files actually present under `test_evidence/`

- `test_evidence/online/README.md` — owner-reported summary and capture template; not primary run evidence or a screenshot.
- `test_evidence/real_run/smoke_embeddings.txt` — earlier operator-provided embedding smoke record.
- `test_evidence/real_run/smoke_ollama.txt` — earlier single-call Ollama smoke record.

No files are present under `test_evidence/offline/` or `test_evidence/ollama_outage/`, and no screenshot image is present under `test_evidence/` in this checkout. Three static dashboard captures exist under `docs/images/` (`dashboard.png`, `dashboard-selected.png`, `dashboard-mobile.png`); they are not target-run evidence. The owner's screen recording is not stored here. Do not invent filenames or claim missing artifacts exist.

## Remaining work

1. The owner confirms the reported Windows-run date as 2026-11-26 (local time, IST), after the 2026-11-23 UTC workspace snapshot. The owner supplied two Drive links, but their roles and contents are unconfirmed; identify the recording and add its footer commit hash if available. Verify the demo corresponds to the final pushed branch commit.
2. Confirm whether `scripts/offline_acceptance.ps1` ran. Preserve and review its actual `.log`/`.json` if available. Confirm the `example.com` probe, ping result, and `netstat` observation; add a network trace or equivalent evidence for the full run. The single probe is not proof that all outbound routes are blocked.
3. Run or provide evidence for the controlled Ollama stop/queue/restart/replay test and unavailable-model message. The outage result is unresolved; do not treat mock queue tests as live proof.
4. The offline two-product ICP comparison and target-run confirmation that a draft remained `sent=false` are still pending. The owner reported generation workflows, but did not explicitly supply those specific checks or records.
5. Complete target-specific licence review. Exact model artifacts/digests, the all-MiniLM-L6-v2 model revision/card, the linked target SQLite runtime, Ollama distribution, and the Windows-resolved dependency set remain **VERIFY**. Official page links are listed in [`MODELS_AND_LICENCES.md`](MODELS_AND_LICENCES.md) and [`SUBMISSION.md`](SUBMISSION.md).
6. GitHub Actions passed on Python 3.11 and 3.12 in push runs `45707464736` and `45708213250`; both matrix jobs passed in each. The pull-request run also passed (`45707489154`), and public repository access was confirmed. Held-out evaluation remains optional roadmap work and should run only after prompts are reviewed/frozen.

## Confidence limits

- **Good confidence:** deterministic logic and local-boundary behavior covered by the automated suite, model-tag preflight and failure reporting, evidence-validator regression coverage, and successful frontend production build.
- **Owner-reported only:** live `qwen3:4b` inference, GPU/CPU split, FieldNest workflow results, and the Wi-Fi-disconnected eight-workflow run. These were not independently verified from files in this checkout.
- **Not established by workspace evidence:** PowerShell script execution on Windows, full network isolation, the ping/listener observations, outage recovery, the demo artifact/footer hash, screenshots, model-quality metrics for this run, or target Windows licence resolutions.

See [`SUBMISSION.md`](SUBMISSION.md) for the six-step run instructions and licence-check page list, [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) for operator steps, and [`ACCEPTANCE_CHECKLIST.md`](ACCEPTANCE_CHECKLIST.md) for the detailed status gates.
