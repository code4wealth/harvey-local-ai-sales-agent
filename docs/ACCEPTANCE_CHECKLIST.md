# Assignment acceptance checklist

This checklist separates checks performed in the repository from live acceptance
that still must be demonstrated on the target laptop.

Status key: `[x]` verified in this workspace or explicitly owner-confirmed for
the stated scope; `[ ]` remains unverified. Owner-reported results are labeled
and are not independently verified by this checkout. A passing unit test or
build is not the same as a real Ollama or internet-off run.

## Automated checks and source review

- [x] `make verify` passed locally: **250 passed, 2 skipped**. The no-cloud
  guard and sample-corpus validation passed. The two skips are PowerShell parser
  tests because PowerShell is not installed in this workspace.
- [x] The source-level no-cloud guard passed. Model inference is fixed to local
  Ollama; this is a source/test check, not a packet capture.
- [x] `.env.example` contains no API credentials. No cloud AI keys are needed.
- [x] The React production bundle builds and is checked in under
  `frontend/static`; the Windows runtime does not need npm to serve it.
- [x] The PowerShell acceptance source declares exactly eight workflows in
  order: business profile, ICP, research from saved page data, signals, problem
  statement, scoring, unsent draft, and reply classification. The full product
  pipeline is a separate API workflow, not a ninth acceptance entry. Static
  tests check the order and timestamped evidence paths for both scripts.
- [x] Source review confirms the offline script makes one non-AI HTTPS request
  to `example.com` as a connectivity indicator. An HTTP response marks the run
  as not offline; failure is not proof that all internet access is blocked.
- [x] Mocked client tests verify `think=false`, Ollama structured output via the
  Pydantic JSON schema, and the 300-second default timeout.
- [x] Pipeline tests verify the default three-prospect snapshot, a configured
  per-run limit, and skips of dependent steps after profile/ICP failure.
- [x] The sample-reply POST endpoint imports the checked-in text-only CSV
  idempotently; database tests confirm no ground-truth label columns are added.
- [ ] Run both PowerShell acceptance scripts on the target Windows laptop.
- [x] Owner reports that all eight workflows completed with Wi-Fi disconnected
  on the target Windows laptop and that the run was screen-recorded (owner-
  confirmed reported date: 2026-11-26, later than the 2026-11-23 workspace
  snapshot). The recording was not supplied into this checkout; no offline run
  log or JSON is present here.
- [ ] Preserve and review the actual timestamped `test_evidence/offline/` log
  and JSON, or equivalent run evidence. Exact filenames were not supplied; do
  not create or claim them from this report.
- [ ] Capture a network trace or equivalent evidence during the complete
  pipeline showing AI traffic only to `127.0.0.1:11434`.
- [ ] Capture current full-pipeline inference logs for every workflow call.

## Owner-reported target-laptop runs

Windows runs: owner-reported, 2026-11-26 (local time, IST). The workspace snapshot carries earlier timestamps (2026-11-23 UTC); the runs were performed afterwards. The date field is owner-confirmed; the outcomes are not independently inspected acceptance artifacts.

- Local inference: `qwen3:4b` through Ollama. The owner reports `ollama ps`
  placement of about 66% GPU / 34% CPU on an RTX 3050, with 15.7 GB RAM and
  12 CPUs. No runtime capture file is present in this checkout.
- Online FieldNest run: profile, ICP, signals, problem statement, draft, and
  ranking completed; 20 prospects and 60 sample replies imported. The owner
  reports `R004` classified `not_interested`, matching its ambiguous
  development label (`data/eval/reply_labels.csv` confirms the label only).
- Offline run: all eight workflows reportedly worked with Wi-Fi disconnected
  and were screen-recorded. The script used, run log/JSON, ping result, and
  `netstat` capture were not supplied; none is present in this checkout.

Files currently present under `test_evidence/` are exactly:

- `test_evidence/online/README.md` — capture template, not screenshot evidence.
- `test_evidence/real_run/smoke_embeddings.txt` — earlier operator-provided
  embedding smoke record.
- `test_evidence/real_run/smoke_ollama.txt` — earlier single-call Ollama smoke
  record.

No files are present under `test_evidence/offline/` or
`test_evidence/ollama_outage/`, and no screenshot image is present under
`test_evidence/` in this checkout. Three static dashboard images exist under
`docs/images/` (`dashboard.png`, `dashboard-selected.png`, and
`dashboard-mobile.png`); they are not target-run evidence. Do not infer that the
owner's screen recording or other capture is stored in `test_evidence/`.

## Live offline acceptance — owner-reported run; evidence review pending

- [x] Business profile generation from local product information — owner reports
  this completed in the Wi-Fi-disconnected eight-workflow run; no run log is in
  this checkout.
- [x] Product-specific ICP generation for the selected product — owner reports
  this completed in the Wi-Fi-disconnected eight-workflow run.
- [ ] Product-specific ICP generation for two products; confirm the results
  differ appropriately. A two-product offline comparison was not confirmed.
- [x] Prospect research from already-saved local page text — owner-reported as
  part of the eight workflows.
- [x] Buying-signal extraction from saved local text — owner-reported as part
  of the eight workflows.
- [x] Evidence-grounded problem statement generation — owner-reported as part
  of the eight workflows.
- [x] Product-specific ranking/scoring — owner-reported as part of the eight
  workflows.
- [x] Personalised email draft generation — owner-reported as part of the
  eight workflows.
- [ ] Verify the target draft remained unsent (`sent=false`) in the saved run;
  the owner did not explicitly confirm this result or supply a record.
- [x] Reply classification on local sample conversations — owner-reported as
  part of the eight workflows. The separate online `R004` result is recorded
  above and should not be recast as an offline result.

The owner reports live local inference, but no per-workflow inference traces,
model-quality metrics, or target-run evidence files were supplied. The current
automated suite still uses mocked Ollama responses and fake embeddings; those
checks are not live proof.

## Failure handling — not yet demonstrated live

The owner's outage/recovery field was left as an unresolved choice; no outage
log or result was supplied. All items in this section remain **PENDING**.

- [ ] Stop Ollama: show a clear error, queued AI task, and working deterministic
  ranking without any cloud fallback.
- [ ] Restart Ollama: show the queue resumes and the original task completes.
- [ ] Request an unavailable model: show the helpful local `ollama pull` message.
- [ ] Save the timestamped `test_evidence/ollama_outage/` log and JSON.

## Demo and submission

- [x] Public fork exists: https://github.com/code4wealth/harvey-local-ai-sales-agent
- [x] Local setup and the local-only API binding are documented in `README.md`.
- [x] Sample data and preview/simulated behavior are labelled in the application.
- [ ] Record and link the 5–10 minute end-to-end demo, including the internet-
  off test. An offline screen recording is owner-reported, but no video URL was
  supplied and no recording file is present in this checkout.
- [ ] Ensure the recorded demo footer matches the final pushed commit; the demo
  footer hash was not supplied. Create a release tag only after verification.
- [ ] Add the final acceptance logs and actual target-run screenshots to the
  submission. No screenshot image is present under `test_evidence/`; the three
  static `docs/images/` dashboard captures are not target-run evidence. No
  offline/outage log is present in this checkout; earlier smoke logs are not
  substitutes for those artifacts.
