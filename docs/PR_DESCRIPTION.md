# PR description

## Summary

Completes the product-specific deterministic ranking and workflow roadmap on the
active Arena branch:

- Keeps the inference boundary local to Ollama; deterministic temperature/seed/repeat-penalty
  defaults and exact product-name profile-summary validation are in place.
- Keeps reply ground truth isolated in `data/eval/reply_labels.csv`; runtime
  reply records and prompts contain text only.
- Adds the eight-label reply classifier and redacted evaluator. The evaluator
  defaults to the 36-reply development set, reports per-label/per-difficulty
  accuracy and a confusion matrix, lists misclassified IDs only, writes reports
  under `test_evidence/real_run/`, and refuses held-out evaluation without a
  matching frozen prompt hash.
- Adds deterministic product-specific prospect ranking using the stored ICP,
  local page text, and valid signals from the latest successful signal run.
- Adds a persisted unsent-draft workflow using only the stored product profile
  and verified signals. Evidence must be verbatim in both stored signals and
  draft body; invalid outputs retry twice and persist failure. With no verified
  evidence, drafting skips inference and records `no verified evidence`.
- Adds product-scoped POST/GET draft API routes and mocked tests. Email is never
  transmitted.
- Serves a static, no-build, no-external-network dashboard from `/`; all browser
  requests use relative same-origin API paths.
- Updates workflow, architecture, limitations, demo, and setup documentation.

## Validation

- `PATH="$PWD/.venv/bin:$PATH" make verify` — passed; corpus checks and **144 tests**.
- `git diff --check` — passed.
- Signal-extraction prompt SHA-256 remains
  `73fa8d3444e458a90d67b641ea93712faf42b6a4f198b86510a6ff82f269ca71`.
- Reply prompt hash frozen to
  `c4ba5ffa86e06b9e0c78bdccb656873f046c8b90755ec895e58b08b49347de3c`.
- No live Ollama run and no held-out evaluation were performed. Reply evaluator
  tests use mocked Ollama HTTP responses.

## Manual follow-up

Run the commands in `docs/DEMO.md` with local Ollama and replace its
`RESULT: fill after live run` placeholders with observed outcomes. Do not claim
mocked test responses as live-model results. Held-out evaluation remains gated
and was not run.
