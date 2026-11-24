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

- `PATH="$PWD/.venv/bin:$PATH" make verify` — passed; corpus checks and **152 tests**.
- `git diff --check` — passed.
- Signal-extraction prompt SHA-256 remains
  `73fa8d3444e458a90d67b641ea93712faf42b6a4f198b86510a6ff82f269ca71`.
- Reply prompt hash frozen to
  `c4ba5ffa86e06b9e0c78bdccb656873f046c8b90755ec895e58b08b49347de3c`.

## Reported live results

Reported configuration: `qwen3:4b`, temperature `0`, seed `42`,
`repeat_penalty=1.0`, Windows laptop, about 18 tokens/s. Missing result values
are marked `not run`; supplied run counts are listed separately.

- Signals, development: summary lines — not run.
- Signals, held-out: 12 pages, one run; summary lines — not run.
- Replies, development (36): per-label accuracy — not run; per-difficulty
  accuracy — not run.
- Replies, held-out (24, one run): per-label accuracy — not run;
  per-difficulty accuracy — not run.
- Profile and ICP: both products produced filled, different ICPs; company size
  was null for both.

No held-out reply or page text is included. All data is fictional SAMPLE data.

## Manual follow-up

`docs/DEMO.md` records the supplied live snapshot and marks missing results as
`not run`. Reply evaluator tests use mocked Ollama HTTP responses; do not
present them as live-model results. The two held-out sets were run once; do not
rerun them as part of routine verification or include held-out text.
