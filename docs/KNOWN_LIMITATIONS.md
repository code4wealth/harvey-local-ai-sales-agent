# Known limitations

## Deterministic title fit

Title fit is a token heuristic, not an org-chart or synonym model. Contact-title
modifiers (`intern`, `assistant`, `associate`, `junior`, `former`, `ex`, and
`student`) cap the result at 20, and seniority-only overlap does not earn the
influencer score. Other modifiers, unusual title spellings, abbreviations,
regional conventions, and genuine role equivalences may still be misclassified.
No external title dictionary or LLM is consulted.

## Local page embeddings

MiniLM-L6 has a model `max_seq_length` of 256 word pieces and silently truncates
longer inputs. Page text is split on whitespace into chunks of about 800
characters; at most six chunks are embedded, averaged, and renormalized. Text
after the sixth chunk is omitted, and averaging loses chunk order and local
context. An individual unusually long token can also exceed the approximate
character target before the model's token limit is applied.

The embedding model is loaded lazily. A failed model load is not cached, so a
later request tries loading again; when the model is not cached and the machine
is offline, repeated requests can incur model-hub timeouts before scoring falls
back to a partial result. This repeated-load behavior is accepted. Set
`HF_HUB_OFFLINE` in the shell before starting Python if an offline load is
intended; changing it after importing the embedding/model libraries may be too
late for their network configuration.

## Profile and ICP grounding heuristics

Profile grounding is a lexical heuristic, not a semantic entailment model. It
normalizes case and common English inflections, removes a small stop-word set,
and compares distinct content words against the company-info source. General
profile claims require at least 60% overlap; each non-`not stated`
`pain_points_solved` item requires at least **80%**. This reduces unsupported
pain claims, but can accept a partially invented sentence or reject a valid
paraphrase that uses different vocabulary. Invalid outputs are sent back for
up to two retries; a response that still fails grounding is not saved.

ICP list items use an 80% content-word overlap against field-specific profile
support: industries use `summary`, `value_proposition`, `typical_team_size`,
and `working_situation`; buyer titles use `typical_buyer`; pain points use
`pain_points_solved` and `working_situation`; trigger events use the stated
profile context; disqualifiers use `not_for`. Numeric company-size bounds must
appear as digits in `typical_team_size`. A small event-verb check and overlap
heuristic reject trigger events that merely restate product features, but
neither is a semantic classifier. Unsupported list fields can be empty or
`not stated`; unsupported company size remains `null`.

Previously stored business profiles remain readable. Missing newly introduced
profile fields are supplied as `not stated` for ICP generation without
rewriting the original stored JSON.

## Signal evaluation and reply labels

The signal evaluator freezes a normalized prompt-template SHA-256 for held-out
runs (the dynamic UTC date is normalized out of the hash). This detects prompt
text drift, not changes to the evaluator, local model weights, or Ollama
implementation. `think=false` and `num_ctx=4096` are reported per run. Model
`none` counts are inferred from the persisted `type` drop counter; rejected
positive candidates are summarized as exercised traps. Detailed results are
saved locally under `test_evidence/real_run/` and are not model-independent
benchmarks.

Reply texts are intentionally separate from operator-authored labels. The
optional `data/sample/reply_labels.csv` is not included by default; no reply
accuracy can be measured until the operator supplies that ground truth.
