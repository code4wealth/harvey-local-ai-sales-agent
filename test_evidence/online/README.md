# Online demo evidence notes — owner report and capture template

**Owner-reported, not independently verified.** The owner confirms the
reported Windows-run date as 2026-11-26. That is later than the current
workspace snapshot/system date (2026-11-23 UTC), so the run remains a
future-dated owner report rather than an outcome verified from target-run
artifacts. The online workflow report is recorded below, but this file remains
a capture template, not primary run evidence. No target-run screenshot or
timestamped online log is present in this directory. Three static dashboard images under `docs/images/` are not evidence
from the reported run. Do not invent results or present SAMPLE data as real
prospect research.

## Owner-reported online result

- Product: FieldNest (SAMPLE product).
- The owner reports profile, ICP, signals, problem statement, draft, and ranking
  completed; 20 prospects and 60 sample replies imported.
- The owner reports `R004` classified `not_interested`, matching the ambiguous
  development label in `data/eval/reply_labels.csv`. The checked-in file
  verifies the label only, not the live inference result.
- The owner reports local inference using `qwen3:4b` via Ollama. Current model
  digest, Ollama version, run ID, and per-workflow logs were not supplied.
- Exact date/time, demo commit, runtime captures, and screenshot files were not
  supplied. This directory contains only this README.

## Run details (complete after capture)

- Capture date/time and timezone: `[not recorded]`
- Repository branch and commit: `[not recorded]`
- Target laptop / Windows and PowerShell versions: `[not recorded]`
- Internet state during this online run: `[not recorded]`
- Ollama version: `[not recorded]`
- Exact generation model tag and digest: `[not recorded]`
- Embedding model revision/cache used: `[not recorded]`
- Product: `[SAMPLE RelayCue / SAMPLE FieldNest / not selected]`
- Prospect ID and `SAMPLE` source page: `[not recorded]`
- Pipeline/workflow run ID(s): `[not recorded]`
- Actual elapsed time: `[not recorded]`
- Evidence reviewer and notes: `[not recorded]`

An online browser demo still uses the application's local Ollama endpoint at
`127.0.0.1:11434`; “online” describes the laptop's network state, not a hosted
AI path. Do not run the optional public-page collector unless that separate
collection is explicitly intended and documented.

## Screenshots to capture

Capture genuine screenshots from the running target laptop. Suggested names
below are placeholders; record the actual filenames and paths. Keep real files in
this directory, use only fictional SAMPLE data, and retain visible failures or
skips rather than hiding them.

| Done | Suggested filename | Capture |
|---|---|---|
| `[ ]` | `01-local-status.png` | `/operations` with the actual API/Ollama status and selected model visible; confirm the displayed Ollama endpoint is loopback if the UI shows it. |
| `[ ]` | `02-sample-product-and-prospects.png` | Selected fictional product and imported SAMPLE prospect list; note the source CSV and prospect IDs in the run details above. |
| `[ ]` | `03-pipeline-controls.png` | `/operations` product selector, prospect limit, **Run full product workflow**, and **View latest progress** controls before a real run. |
| `[ ]` | `04-saved-pipeline-progress.png` | The actual saved run after completion or failure, including per-step states and run ID. Do not imply a failed/partial run succeeded. |
| `[ ]` | `05-verified-signals.png` | One SAMPLE prospect's actual signal type/status and its verified quoted evidence, if available. Do not substitute evaluator labels or fixture text. |
| `[ ]` | `06-problem-statement.png` | The actual generated or skipped problem-statement status and evidence count/quotes as displayed; retain the exact wording and any failure state. |
| `[ ]` | `07-ranking-explanation.png` | Actual ranking results and score components, including any missing/unknown inputs. |
| `[ ]` | `08-unsent-email-draft.png` | Actual subject, body, cited evidence, and visible `Not sent` / `sent=false` status. Never click a send action; the app is intended to save drafts only. |
| `[ ]` | `09-sample-reply-classification.png` | Actual classification for SAMPLE reply `R001` (or record the selected reply ID), with its status and confidence if shown. |
| `[ ]` | `10-local-runtime-placement.png` | Actual terminal output from `ollama ps`, `netstat -ano | findstr ":11434"`, and `nvidia-smi` if available. If CPU/GPU placement is absent or unclear, write “not reported”; do not infer a split. |

## Capture log

For each screenshot, complete one entry. Leave the entry blank until a real image
exists in this directory.

### Screenshot 01

- Actual filename/path: `[not captured]`
- Capture time: `[not recorded]`
- Page/command and state shown: `[not recorded]`
- Run ID / product / SAMPLE prospect, if applicable: `[not recorded]`
- What the image does **not** prove: `[not recorded]`
- Review/redaction notes: `[not recorded]`

### Screenshot 02

- Actual filename/path: `[not captured]`
- Capture time: `[not recorded]`
- Page/command and state shown: `[not recorded]`
- Run ID / product / SAMPLE prospect, if applicable: `[not recorded]`
- What the image does **not** prove: `[not recorded]`
- Review/redaction notes: `[not recorded]`

### Additional screenshots

Copy the six-field entry above for each actual screenshot. Keep the original capture
unchanged; if a redacted copy is needed for sharing, retain and identify it as a
separate derivative. Screenshots are not a substitute for the timestamped
PowerShell `.log`/`.json` files in `test_evidence/offline/` and
`test_evidence/ollama_outage/`.

## Limitations and result summary (complete after run)

- Workflows actually run and their observed statuses: `[not recorded]`
- Failures, skips, retries, or incomplete steps: `[not recorded]`
- `ollama ps` CPU/GPU placement, if reported: `[not recorded]`
- Network/offline checks performed (if any): `[not recorded]`
- What remains **PENDING**: `[not recorded]`
- Link/path to actual timestamped logs and JSON: `[not recorded]`

No screenshots, physical-device outcomes, benchmarks, or model outputs have been
created by this template.
