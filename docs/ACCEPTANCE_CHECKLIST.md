# Assignment acceptance checklist

This checklist separates checks performed in the repository from live acceptance
that still must be demonstrated on the target laptop.

Status key: `[x]` verified for the stated scope; `[ ]` not yet demonstrated.
A passing unit test or build is not the same as a real Ollama or internet-off run.

## Automated checks and source review

- [x] `make verify` passed locally: **234 passed, 2 skipped**. The no-cloud
  guard and sample-corpus validation passed. The two skips are PowerShell parser
  tests because PowerShell is not installed in this workspace.
- [x] The source-level no-cloud guard passed. Model inference is fixed to local
  Ollama; this is a source/test check, not a packet capture.
- [x] `.env.example` contains no API credentials. No cloud AI keys are needed.
- [x] The React production bundle builds and is checked in under
  `frontend/static`; the Windows runtime does not need npm to serve it.
- [x] The PowerShell acceptance source declares the required order: business
  profile, ICP, research from saved page data, signals, problem statement,
  scoring, draft, reply classification, then the full pipeline as an extra.
  Static tests check the order and timestamped evidence paths.
- [x] Source review confirms the offline script makes one non-AI HTTPS request
  to `example.com` as a connectivity indicator. An HTTP response marks the run
  as not offline; failure is not proof that all internet access is blocked.
- [ ] Run both PowerShell acceptance scripts on the target Windows laptop.
- [ ] Run the complete workflow with Wi-Fi/internet disconnected and save the
  resulting `test_evidence/offline/` log and JSON. No such acceptance files are
  present yet.
- [ ] Capture a network trace or equivalent evidence during the complete
  pipeline showing AI traffic only to `127.0.0.1:11434`.
- [ ] Capture current full-pipeline inference logs for every workflow call.

## Live offline acceptance — not yet run

- [ ] Business profile generation from local product information.
- [ ] Product-specific ICP generation for two products; confirm the results
  differ appropriately.
- [ ] Prospect research from already-saved local page text.
- [ ] Buying-signal extraction from saved local text.
- [ ] Evidence-grounded problem statement generation.
- [ ] Product-specific ranking/scoring.
- [ ] Personalised email draft generation and confirmation it remains unsent.
- [ ] Reply classification on the local sample conversations.

The repository contains an earlier operator-provided Qwen3 smoke log, but that
is only a single local model call, not this full offline acceptance test. No
real Ollama inference was run for the current code changes or in the current
verification suite.

## Failure handling — not yet demonstrated live

- [ ] Stop Ollama: show a clear error, queued AI task, and working deterministic
  ranking without any cloud fallback.
- [ ] Restart Ollama: show the queue resumes and the original task completes.
- [ ] Request an unavailable model: show the helpful local `ollama pull` message.
- [ ] Save the timestamped `test_evidence/ollama_outage/` log and JSON.

## Demo and submission

- [x] Public fork exists: https://github.com/code4wealth/harvey-local-ai-sales-agent
- [x] Local setup and the local-only API binding are documented in `README.md`.
- [x] Sample data and preview/simulated behavior are labelled in the application.
- [ ] Record the 5–10 minute end-to-end demo, including the internet-off test.
- [ ] Ensure the recorded demo matches the final pushed commit; create a release
  tag only after that version is verified.
- [ ] Add the final acceptance logs and any screenshots to the submission. The
  existing smoke logs and dashboard screenshots do not replace the offline
  acceptance evidence or the required video.
