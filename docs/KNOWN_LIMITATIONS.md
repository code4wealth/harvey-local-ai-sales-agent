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

The signal evaluator uses a normalized prompt-template SHA-256 for held-out
runs (the dynamic UTC date is normalized out of the hash). The operator freezes
it explicitly with standalone `--freeze-prompt`; replacing a different hash
requires `--refreeze`. Development runs do not read or write the hash file, and
held-out runs only read and enforce it. This detects prompt-text drift, not
changes to the evaluator, local model weights, or Ollama implementation.
`think=false` and `num_ctx=4096` are reported per run. Model-empty-list counts
come only from successfully parsed empty `signals` arrays; returned signals
that are later filtered are counted separately with per-reason drops. Held-out
reports retain run configuration plus IDs and counts, with no raw replies,
evidence, or page text. Development diagnostics, including raw model replies,
are saved locally under `test_evidence/real_run/` and are not
model-independent benchmarks.

Reply texts and labels stay separate: sample text is in
`data/sample/replies.csv`, and labels are in `data/eval/reply_labels.csv`. The
classifier never receives reply IDs, labels, difficulty, or split metadata. The
offline evaluator defaults to the 36 development examples, writes reports
without raw text or rationale, and requires a matching frozen prompt hash before
it can load held-out labels/text. Hashing detects prompt-text changes only; it
does not freeze model weights, Ollama, decoding implementation, or evaluator
code. All replies are synthetic SAMPLE examples, so their accuracy is not a
customer-data benchmark. The supplied live run used `qwen3:4b` at temperature
`0`, seed `42`, repeat penalty `1.0`, on a Windows laptop at about 18 tokens/s.
The 12-page signal held-out set and the 24-example reply held-out set were each
run once. Signal development and held-out summary lines, plus reply per-label
and per-difficulty accuracy values for development (36) and held-out (24), were
not supplied and are recorded as `not run` here. Both products produced filled,
different ICPs; company size was null for both.

The 4B model is non-deterministic across seeds. It occasionally emits stray
repeated-token artifacts, caught by quote verification and the artifact check.
It could not reliably reproduce a product name, so profile summaries omit it;
the display name comes from the products table. Signal development scores are
optimistic because the prompt was revised after seeing development failures.
Held-out sets are small, so per-label numbers are rough. All data is fictional
SAMPLE data.

## Product-specific ranking

Ranking is deterministic and intentionally lexical for several ICP-field
matches. It can miss a legitimate paraphrase or count an incidental phrase; it
is an auditable prioritization aid, not a semantic buyer-fit judgement. It uses
the latest successful signal run and reports a newer failed run separately.
Missing inputs remain visible and can produce partial or unranked results.

## Evidence-grounded outreach drafts

A draft's evidence check proves that each listed quote is an exact string in a
stored verified signal and occurs verbatim in the body. It does not prove that
every unquoted sentence is semantically entailed by the product profile or
prospect page. The prompt instructs the model not to invent facts, but language
models can still produce unsupported copy. Review drafts before use. The
workflow only persists unsent drafts; it has no email-send capability.
