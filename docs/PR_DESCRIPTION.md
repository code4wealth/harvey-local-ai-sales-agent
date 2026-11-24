# PR description

## Summary

Completes the product-specific deterministic ranking and workflow roadmap on the
active Arena branch:

- Keeps the inference boundary local to Ollama, with deterministic temperature/seed/repeat-penalty
  defaults; product display names come from the products table rather than model-written summaries.
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

- `PATH="$PWD/.venv/bin:$PATH" make verify` — passed; corpus checks and **154 tests**.
- `git diff --check` — passed.
- Signal-extraction prompt SHA-256 remains
  `73fa8d3444e458a90d67b641ea93712faf42b6a4f198b86510a6ff82f269ca71`.
- Reply prompt hash frozen to
  `c4ba5ffa86e06b9e0c78bdccb656873f046c8b90755ec895e58b08b49347de3c`.

## Reported live results

Configuration: `qwen3:4b`, temperature `0`, seed `42`, `repeat_penalty=1.0`,
retry temperature `0.2`, Windows laptop, about 18 tokens/s. Unavailable run
outputs are marked `not run`; unreported outcomes are marked `not supplied`.

- Signals, development (37 prospects; signal prompt hash prefix `73fa8d34...`):
  expected-signal recall `14/16 (87.5%)`; `34/37` prospects passed; `1` false
  positive on an implied-signal page (`P010`); misses `P001` (quote glitch
  persisted after `2` quote retries) and `P022` (model returned nothing); `8`
  quote-verification retries in total.
- Signals, held-out (12 pages, one run): expected-signal recall `8/8 (100%)`;
  `9/12` passed (failed `P045`, `P047`, `P049`); false positives: no-signal/
  implied `1`, negated `1`, other-company `1`; stale-signal trap held; empty-list
  returns `0/12`; `4` quote drops, `2` negated drops.
- Replies, development before one prompt revision (36): `27/36 (75.0%)`;
  wrong_person `1/4`, other `1/4`, interested `3/5`.
- Replies, development after the revision (36): `32/36 (88.9%)`; ambiguous
  `9/10`, clear `23/26`; misclassified IDs `R025`, `R028`, `R039`, `R043`.
- Replies, held-out (24, one run; prompt frozen, hash prefix `a369052a...`):
  `18/24 (75.0%)`; per-label counts: interested `2/3`, meeting_request `2/3`,
  not_interested `2/3`, other `1/3`, out_of_office `3/3`, question `2/3`,
  unsubscribe `3/3`, wrong_person `3/3`; ambiguous `6/10 (60%)`, clear
  `12/14 (85.7%)`; misclassified IDs `R014`, `R018`, `R019`, `R048`, `R050`,
  `R060`.
- Profile and ICP: RelayCue profile and ICP succeeded. FieldNest ICP succeeded
  on the final run (HTTP 200); an earlier run failed grounding after the model
  invented a trigger event and disqualifier, and the failure was stored with
  its reason.
- Demo behavior: ranking returned an explicit missing-input status when no
  signal run exists; the draft was skipped with reason `no verified evidence`
  and was never sent; reply classification of `R001` returned `interested`.

No held-out reply or page text is included. All data is fictional SAMPLE data.

## Manual follow-up

`docs/DEMO.md` records the supplied live snapshot and marks unavailable runs as
`not run` and unreported outcomes as `not supplied`. Reply evaluator tests use
mocked Ollama HTTP responses; do not present them as live-model results. The two
held-out sets were run once; do not
rerun them as part of routine verification or include held-out text.
