# PR description

## Summary

- Keeps AI inference local to Ollama and the dashboard on same-origin API paths.
- Keeps reply ground truth isolated; the reply evaluator reports aggregates and
  misclassified IDs without including reply text or rationale.
- Adds deterministic product-specific ranking using stored ICP, local page text,
  and valid signals from the latest successful signal run.
- Adds product-scoped profile, ICP, signal, reply-classification, and draft
  workflows with persisted runs and retry/failure handling.
- Draft evidence uses one or two 4-to-15-word spans, each checked as a substring
  of this prospect's verified signal evidence and the body after case and
  whitespace normalization only; each span must be enclosed in double quotes.
  Drafts are stored with `sent=false`.
- Updates the demo, limitations, setup, and workflow documentation with reported
  results and explicit limitations.

## Validation

- `make verify` — passed; corpus checks and **156 tests**.
- `git diff --check` — passed.

## Reported live results

Configuration: `qwen3:4b`, temperature `0`, seed `42`, `repeat_penalty=1.0`,
retry temperature `0.2`, Windows laptop, about 18 tokens/s. All data is fictional
`SAMPLE` data.

- Signals, development (37 prospects; prompt hash prefix `73fa8d34...`):
  expected-signal recall `14/16 (87.5%)`; `34/37` passed; one implied-signal
  false positive (`P010`); misses `P001` (quote glitch persisted after two quote
  retries) and `P022` (model returned nothing); `8` quote-verification retries.
- Signals, held-out (12 pages, one run): recall `8/8 (100%)`; `9/12` passed
  (`P045`, `P047`, `P049` failed); one false positive in each of the
  no-signal/implied, negated, and other-company trap categories; stale-signal
  trap held; empty-list return on `0/12`; `4` quote drops and `2` negated drops.
- Replies, development before one prompt revision (36): `27/36 (75.0%)`;
  wrong_person `1/4`, other `1/4`, interested `3/5`.
- Replies, development after the revision (36): `32/36 (88.9%)`; ambiguous
  `9/10`, clear `23/26`; misclassified IDs `R025`, `R028`, `R039`, `R043`.
- Replies, held-out (24, one run; prompt frozen, hash prefix `a369052a...`):
  `18/24 (75.0%)`; interested `2/3`, meeting_request `2/3`, not_interested
  `2/3`, other `1/3`, out_of_office `3/3`, question `2/3`, unsubscribe `3/3`,
  wrong_person `3/3`; ambiguous `6/10 (60%)`, clear `12/14 (85.7%)`;
  misclassified IDs `R014`, `R018`, `R019`, `R048`, `R050`, `R060`.
- Profile and ICP: RelayCue profile and ICP succeeded. FieldNest ICP succeeded
  on the final run (HTTP 200); an earlier run failed grounding on an invented
  trigger event and disqualifier, and its failure reason was stored.
- Signals ran for all `41` prospect rows (`21` RelayCue, `20` FieldNest);
  rankings were saved under `test_evidence/real_run/`. Ranking reports an
  explicit missing-input status when no signal run exists. Classification of
  `R001` returned `interested` with confidence `0.95`.
- Drafts, first attempt (`9` prospects): `6` skipped with `no verified evidence`,
  `3` failed the verbatim-evidence check because the model paraphrased; none
  were sent.
- Drafts after the fix (`6384b4b`, `156` tests), across `21` RelayCue prospects:
  `7` succeeded (IDs `22`, `28`, `30`, `32`, `34`, `35`, `36`), `12` skipped with
  `no verified evidence`, and `2` failed (`25`, `37`) with stored reasons. All
  had `sent=false`; FieldNest drafts were not run. In the successful example for
  prospect `22`, a four-word verified span was quoted in the body.

## Limitations

The reply prompt was revised once after seeing development results, so the
held-out score (`75.0%`) is the honest one; the `13.9`-point drop from
development is expected. Held-out per-label counts are `3`, so each reply moves
a label by `33` points. Signal extraction over-extracts on held-out pages: there
were `3` trap false positives and `0/12` empty lists despite perfect recall, so
trap-page precision is the main weakness. Signal development scores are
optimistic because the prompt was revised after seeing development failures.

The 4B model is non-deterministic across seeds and sometimes emits repeated-token
artifacts, caught by quote verification and the artifact check; quote retries
did not always fix the issue (`P001`). Profile summaries omit the product name
because the model could not reliably reproduce it. Draft validation checks the
quoted evidence spans, not whether other sentences are grounded; spans can be as
short as four words, so human review is required. All data is fictional
`SAMPLE` data.

## Manual follow-up

`docs/DEMO.md` records the supplied run snapshot. It leaves unavailable run
outputs as `not run` and unreported outcomes as `not supplied`. Do not rerun the
held-out evaluators or include held-out reply/page text.
