# Known limitations

## Deterministic title fit

Title fit is a token heuristic, not an org-chart or synonym model. Contact-title
modifiers (`intern`, `assistant`, `associate`, `junior`, `former`, `ex`, and
`student`) cap the result at 20, and seniority-only overlap does not earn the
influencer score. Other modifiers, unusual title spellings, abbreviations,
regional conventions, and genuine role equivalences may still be misclassified.
No external title dictionary or LLM is consulted.

## Stored-page research and crawling

Research uses locally stored page content; BeautifulSoup is the only HTML
parser in use. Scrapy and Playwright are not used. The application does not
perform fresh page crawling or browser automation, so newly collected page
content must be supplied separately.

## Local page embeddings

MiniLM-L6 has a model `max_seq_length` of 256 word pieces and silently truncates
longer inputs. Page text is split on whitespace into chunks of about 800
characters; at most six chunks are embedded, averaged, and renormalized. Text
after the sixth chunk is omitted, and averaging loses chunk order and local
context. An individual unusually long token can also exceed the approximate
character target before the model's token limit is applied.

The embedding model is loaded lazily. A failed model load is not cached, so a
later request tries loading again. The loader sets `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` before importing the model library. If model files are
not cached, loading fails locally and ranking falls back to its existing partial
result; the app does not download them from a model hub. Pre-cache the model
before starting the offline application.

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
customer-data benchmark.

Reported live configuration was `qwen3:4b`, temperature `0`, seed `42`,
`repeat_penalty=1.0`, retry temperature `0.2`, on a Windows laptop at about
18 tokens/s. Signal development (37 prospects; prompt hash prefix `73fa8d34...`)
had expected-signal recall `14/16 (87.5%)`; `34/37` prospects passed, with one
implied-signal false positive (`P010`), misses `P001` (quote glitch persisted
after two quote retries) and `P022` (model returned nothing), and `8`
quote-verification retries. The held-out signal run (12 pages, run once) had
recall `8/8 (100%)` and `9/12` pages passed (`P045`, `P047`, `P049` failed).
There was one trap false positive in each of no-signal/implied, negated, and
other-company categories; the stale-signal trap held, empty lists were `0/12`,
and there were `4` quote drops and `2` negated drops.

Reply development before one prompt revision scored `27/36 (75.0%)`, with
wrong_person `1/4`, other `1/4`, and interested `3/5`. After the revision it
scored `32/36 (88.9%)` (ambiguous `9/10`, clear `23/26`); misclassified IDs were
`R025`, `R028`, `R039`, and `R043`. The held-out reply run (24, run once, prompt
frozen with hash prefix `a369052a...`) scored `18/24 (75.0%)`. Per-label counts
were interested `2/3`, meeting_request `2/3`, not_interested `2/3`, other `1/3`,
out_of_office `3/3`, question `2/3`, unsubscribe `3/3`, and wrong_person `3/3`;
ambiguous was `6/10 (60%)`, clear was `12/14 (85.7%)`, and misclassified IDs
were `R014`, `R018`, `R019`, `R048`, `R050`, and `R060`.

The reply prompt was revised once after seeing development results, so the
held-out score (`75.0%`) is the honest one and the `13.9`-point drop from
development is expected. Held-out per-label counts are `3`, so each reply moves
a label by `33` points. Signal development scores are optimistic because the
signal prompt was revised after seeing development failures. Signal extraction
over-extracts on held-out pages (`3` trap false positives, `0/12` empty lists)
despite perfect recall, so precision on trap pages is the main weakness. The
4B model is non-deterministic across seeds and occasionally emits repeated-token
artifacts; quote verification and the artifact check catch them,
but quote retries did not always fix the issue (`P001`). Profile summaries omit
the product name because the model could not reliably reproduce it. RelayCue
profile and ICP succeeded. FieldNest ICP succeeded on the final run (HTTP 200);
an earlier run failed grounding after the model invented a trigger event and
disqualifier, and that failure was stored with its reason. Signals ran for all
`41` prospect rows (`21` RelayCue, `20` FieldNest), with rankings saved to
`test_evidence/real_run/`. Ranking returns an explicit missing-input status when
no signal run exists. Reply classification of `R001` returned `interested` with
confidence `0.95`. All data is fictional SAMPLE data.

## Product-specific ranking

Ranking is deterministic and intentionally lexical for several ICP-field
matches. It can miss a legitimate paraphrase or count an incidental phrase; it
is an auditable prioritization aid, not a semantic buyer-fit judgement. It uses
the latest successful signal run and reports a newer failed run separately.
Missing inputs remain visible and can produce partial or unranked results.

## Evidence-grounded problem statements

The problem-statement workflow selects the product's latest stored profile and
ICP and the prospect's latest successful signal run. It requires one or two
4-to-15-word spans that occur in both that run's verified evidence and the
one- or two-sentence statement after case and whitespace normalization only.
This exact-span check constrains fabricated quotations, but it is not a semantic
entailment check: it cannot establish that the complete statement, or an
inferred connection between a signal and a product/ICP pain point, is true.
Review generated statements before using them. With no verified evidence the
workflow records `skipped` / `no verified evidence` without model inference;
invalid outputs retry twice and terminal failures are persisted.

## Evidence-grounded outreach drafts

The validator checks that each `evidence_used` span is a substring of this
prospect's stored verified signal evidence and appears in the body inside double
quotes, after case and whitespace normalization only. Generated drafts must
contain `1`–`2` spans of `4`–`15` words. This does **not** verify that other
sentences in the body are grounded in the product profile or prospect evidence.
Spans can be as short as `4` words, so drafts can be weak or include unsupported
pitch sentences; the prompt's grounding instruction does not make the remaining
body semantically verified. Every draft is stored with `sent=false` and requires
human review; the workflow has no email-send capability.

On the first attempt, `9` prospects were tried: `6` drafts were skipped with
`no verified evidence`, and `3` failed the verbatim-evidence check because the
model paraphrased; none were sent. After the fix (`6384b4b`, `156` tests), across
`21` RelayCue prospects, `7` drafts succeeded (IDs `22`, `28`, `30`, `32`, `34`,
`35`, `36`), `12` were skipped with `no verified evidence`, and `2` (`25`, `37`)
failed validation and remain stored as visible failures with reasons. All had
`sent=false`. The example for prospect `22` used and quoted a four-word verified
span and succeeded with `sent=false`. FieldNest drafts were not run.
