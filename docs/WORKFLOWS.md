# Workflows and scoring contracts

This document records the implemented deterministic behavior, local-only LLM
contracts, mocked evaluation tooling, and the remaining live-validation work.
No real Ollama run or held-out evaluation has been performed for the current
workflow milestones; prompt tuning and live results remain operator-owned.

## Implemented deterministic batch

### Products and prospects

- Products are stored locally in SQLite with a name, description, and local
  documentation path. A product owns its prospects.
- CSV import is product-scoped. Headers are case-insensitive; spaces and
  hyphens normalize to underscores. `company_name` is required. Supported
  optional headers are `contact_name`, `contact_title`, `company_domain`,
  `employee_count`, `contact_email`, `page_text_path`, and `do_not_contact`.
  File imports open with `utf-8-sig` for Excel BOMs. Errors identify the row.
  Imports are atomic and skip duplicate companies: within a product, a
  non-empty `company_domain` is compared case-insensitively; if it is empty,
  case-insensitive `company_name` is used. Duplicates already in SQLite and
  earlier in the same CSV are skipped. The API reports `imported` and `skipped`
  counts.
- `page_text_path` must be a relative filename/path resolving inside
  `data/prospect_pages/`, anchored to the repository root from `app/prospects.py`
  rather than the process working directory. Absolute paths and any `..`
  component are rejected on POSIX and Windows. Page text is explicitly
  stored/read as local UTF-8 text. Replacing it clears the cached page
  embedding. The API does not fetch a URL or perform online research. An
  optional operator-run helper, `scripts/fetch_public_pages.py`, can collect
  explicitly supplied public URLs separately; it observes `robots.txt`, saves
  text locally, and is not imported by or connected to the inference path.
- Queue handlers `prospects.import_csv` and `prospects.score` are
  **deterministic** and do not require an Ollama health probe. A slow or
  unavailable probe must not block these local tasks. LLM-dependent handlers
  still wait for Ollama. The score handler embeds persisted flat ICP JSON and
  local page text when their vectors are absent, stores local vectors, then
  scores. If a required vector cannot be computed or loaded, similarity stays
  null and the result is partial.

### Product-level pipeline

- `POST /api/products/{product_id}/pipeline` snapshots the product's currently
  imported prospects and queues one persistent, resumable local run. A second
  POST while that product already has a queued/running pipeline returns the
  active run rather than creating a duplicate. Newly imported prospects are
  included in the next run, not added to an existing snapshot.
- Steps run in order: business profile, ICP, then for each snapshotted prospect
  local-page signal extraction, evidence-grounded problem statement, and
  evidence-grounded unsent draft; product-specific ranking runs last. Page
  text is read only from repository-local prospect files. This is not a scraper
  and does not import CSVs or fetch the web.
- The persistent `pipeline_runs` / `pipeline_steps` records include run status,
  ordered per-prospect step status, timestamps, error/skip reason, and child
  workflow run IDs. `GET /api/pipeline-runs/{run_id}` polls a run;
  `GET /api/products/{product_id}/pipeline` reads the latest one. The dashboard
  exposes a one-click run and saved step-by-step progress.
- If Ollama becomes unavailable during inference, the in-progress child run and
  pipeline step return to `queued`; the same product pipeline resumes at that
  step after worker retry. Completed steps are not repeated. Other per-step
  failures are persisted and do not prevent independent prospects from being
  processed; dependent steps are marked skipped, ranking still runs when
  possible, and the overall run is `failed` if any step failed. No verified
  signal evidence skips problem-statement and draft model calls, while the
  pipeline continues.
- A pipeline is queued only when work is requested; no background research or
  email sending is performed. Drafts remain local and unsent.

### Local embeddings

- `app/embeddings.py` uses the
  `sentence-transformers/all-MiniLM-L6-v2` model and returns normalized local
  vectors. The model is lazy-loaded and cached in-process. Test doubles exist
  only in `tests/`.
- MiniLM-L6 has a `max_seq_length` of 256 word pieces and silently truncates
  longer inputs. `embed_long_text` splits page text on whitespace into chunks
  of about 800 characters, embeds at most six chunks, averages their vectors,
  and renormalizes the result. Text beyond six chunks is omitted.
- The application sets both `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`
  inside the lazy loader before importing the model library. With
  `OFFLINE_STRICT=1`, it also sets `HF_HUB_DISABLE_TELEMETRY=1` and
  `HF_HUB_DISABLE_IMPLICIT_TOKEN=1`; `make offline` enables this mode. Cache the
  model files separately before starting the application; the AI path never
  downloads them. `python scripts/smoke_embeddings.py` reports `max_seq_length` and vector
  dimension only when the model is already available locally. Missing files
  raise `EmbeddingModelUnavailable`, and no embedding output is fabricated.
  Failed model loads are not cached, so a later call retries the local load.

## Quote verification — deterministic

Before checking evidence quotes, normalize both source and candidate quote in
this order:

1. Unicode NFKC normalization.
2. Straighten curly single/double quotes and common Unicode dashes to straight
   ASCII quote characters and hyphens.
3. Collapse every whitespace run to one space and trim.
4. Lowercase.

Retain a quote only if it has at least **8 normalized characters** and at
least **2 whitespace-separated words**, and its normalized text is a substring
of the normalized source. Return the retained normalized quotes and the count
that were dropped. Non-string, empty, too-short, one-word, and unmatched quotes
are dropped; a quote is never repaired by inventing source text.

`verify_signals(source, signals)` verifies each signal's evidence with this
same normalized matching, but returns retained signal objects without changing
their original evidence strings. Its return value is
`(kept_signals, quote_drops, type_drops)`. Types outside `SIGNAL_WEIGHTS`,
including legacy `none` items in older stored runs, are dropped and counted
separately from evidence failures.

## Scoring — explainable hybrid

The API and dashboard expose the component values, weights, weighted points,
missing inputs, model/rule provenance, and evidence-quality audit. Model-derived
inputs are the local embedding vectors used for ICP similarity and the signal
type/confidence returned by signal extraction. The conversions and aggregation
below are deterministic, rule-based steps; they are not model output.

### ICP similarity

The local embedding model produces ICP and prospect-page vectors. A deterministic
cosine-similarity calculation maps them linearly from cosine `0.15 → 0` to
`0.65 → 1`, clamping below and above that interval to `0` and `1`. Embedding
inference is model-derived; cosine calculation, scaling, and score weighting
are rule-based. Missing, mismatched, or zero-length vectors make the component
`null`.

### Signal score

Signal extraction returns model-generated types, confidence values in `[0,1]`,
and evidence quotes. The quote checks against the current stored page are
rule-based. Scoring aggregation is also rule-based: each signal type contributes
at most once, using the highest valid model confidence for that type. The
contribution is `weight × confidence`; the total is capped at 100. The baseline
rule weights are:

| Signal type | Weight |
|---|---:|
| funding | 30 |
| hiring | 25 |
| expansion | 20 |
| pain_mention | 25 |
| leadership_change | 15 |
| tech_change | 15 |

An explicit `none` signal contributes zero. An absent signal record or an
unknown/unweighted type is uncomputable (`null`), not an invented zero.

### Size fit — rule-based

Use the ICP's flat `company_size_min` and `company_size_max` fields and the
prospect's recorded `employee_count`. Fit is 100 inside the inclusive range.
Outside it, let `r` be the ratio to the nearest boundary (`employees / max`
above the range, `min / employees` below it). Fit decays logarithmically as
`100 × (1 − ln(r) / ln(3))`, reaching zero at a 3× ratio. Missing or invalid
inputs make the component `null`.

### Title fit — rule-based

Use only the ICP's `buyer_titles` keywords. A substantive buyer-title phrase
appearing contiguously in the contact title scores 100 (decision-maker); any
remaining non-connector keyword overlap scores 60 (influencer); no substantive
overlap scores 20 (other). Seniority-only overlap (`vp`, `director`, `head`, `manager`,
`chief`, `senior`, `lead`) is not substantive. Contact-title modifiers
(`intern`, `assistant`, `associate`, `junior`, `former`, `ex`, `student`) cap
the score at 20. If the contact title or buyer-title list is missing, the
component is `null`. This remains a deterministic keyword heuristic; see
`docs/KNOWN_LIMITATIONS.md`.

### Overall score and missing inputs — rule-based

The final weighting, partial-score handling, ranking order, and tier thresholds
are deterministic rules; evidence quality is separately exposed as an audit
indicator and does not add points. The complete formula is:

`0.35 × icp_similarity × 100 + 0.35 × signal_score + 0.15 × size_fit + 0.15 × title_fit`

`icp_similarity` is on 0–1; the other components are on 0–100. An
uncomputable component stays JSON `null`, contributes zero to the weighted
sum, appears in `missing_components`, and sets `partial` true. Use the original
weights without re-normalization. If all components are missing, the score is
`0` and `partial` is true. Never substitute guessed inputs or claim a partial
total is complete.

## Product-specific deterministic ranking

`GET /api/products/{product_id}/ranking` ranks only that product's prospects.
It uses the product's stored ICP, local page text, and only valid signals from
the latest successful signal run for each prospect. A later failed extraction
is reported as the latest run state but does not replace the prior successful
signal snapshot. No LLM is called and no missing component is invented.

The response identifies missing inputs/components, deterministic ICP field
matches and supporting evidence reasons, component scores, rank, and tier. Its
`score_explanations` object separates the model-derived embedding/signal inputs
from rule-based title/size fit, quote checks, weighting, and tier logic. It
shows ICP fit, signal strength, and evidence quality; evidence quality is a
rule-based audit metric that is not part of the total. Complete totals map to
`high` at 70+, `medium` at 40+, and `low` below 40; incomplete inputs remain
partial. A product with no usable ICP is unranked with a null score. This route
is distinct from the older batch score writer.

## LLM workflow status

All inference uses the local `app/llm_client.py` path. Every model response is
validated against a Pydantic schema and any workflow-specific grounding checks.
An invalid response gets at most one stricter-prompt retry (two total attempts);
a second invalid response fails and its reason is persisted. Signal quote
verification shares that same retry budget. Transport failures are not hot-loop
retried; local Ollama outages are queued. The first request uses temperature
`0` and seed `42`; the retry uses temperature `0.2` and the next seed.

Implemented:

1. **Business profile:** local company-info document; summary, value
   proposition, key features, pain points solved, differentiators,
   `typical_buyer`, `typical_team_size`, `working_situation`, and `not_for`.
   General claims need 60% normalized content-word overlap with the source;
   each pain-point item needs 80%. Missing fields on previously saved profiles
   are supplied as `not stated` for ICP generation without rewriting the
   stored profile. The summary must omit the stored product name and any
   case-insensitive prefix of four or more characters of that name followed by
   a colon; the display name always comes from the products table, not the model.
2. **ICP:** uses the stored profile's buyer, team-size, working-situation,
   pain-point, and `not_for` fields. Every list item is grounded in its
   field-specific profile support; unsupported lists may be empty or contain
   `not stated`; numeric size bounds require explicit numeric support. A
   trigger must describe a concrete external event, not a product feature.
3. **Buying signals:** local prospect page; `{signals: [...]}` where each
   item is `{type, evidence, confidence, about_company}`. The schema constrains
   confidence to finite `[0,1]`; evidence must be a complete exact sentence in
   the stored page. A single stricter retry covers schema and quote failures;
   unrelated-company, negated, and stale events are filtered before persistence.
   The held-out prompt hash was refrozen for this confidence-field change; no
   held-out model evaluation was run for the update.
4. **Reply classification:** `POST` / `GET /api/replies/{reply_id}/classification`.
   The model sees only stored inbound reply text, not reply ID or evaluation
   metadata. It returns one of eight strict labels, confidence in `[0,1]`, and
   a rationale of at most 200 characters. Invalid results get one stricter
   retry; outage tasks are persisted and replayed. Ground-truth labels are in
   `data/eval/reply_labels.csv`, never in the runtime sample-reply table.
5. **Outreach draft:** `POST` / `GET
   /api/products/{product_id}/prospects/{prospect_id}/draft`. The prompt uses
   only the product's stored business profile and valid signals from the
   latest successful signal run. The draft must include one or two 4-to-15-word
   evidence spans, each a substring of both the prospect's current stored page
   text and verified signal evidence after case/whitespace normalization, quoted
   inside double quotes in the body. The prompt prohibits other prospect claims;
   only cited spans are mechanically verified, so human review remains required.
   Invalid drafts get one stricter retry; persistent failure is returned and
   stored. If no signal quote remains verified against the current page, the
   workflow skips inference and persists a reason. Drafts are local records only;
   no send API exists.
6. **Problem statement:** `POST` / `GET
   /api/products/{product_id}/prospects/{prospect_id}/problem-statement`. It
   uses the product's latest stored business profile and ICP plus this
   prospect's valid signals from the latest successful signal run. It persists
   those source IDs and up to two verbatim 4-to-15-word evidence spans. Every
   span must occur in both the verified signal evidence and the one- or
   two-sentence statement after case and whitespace normalization only.
   Invalid model results get one stricter retry; terminal failures are persisted,
   and Ollama-unavailable runs are queued for worker retry. With no verified
   evidence, it stores `skipped` / `no verified evidence` and does not resolve
   or call a model. The dashboard can generate and view the latest result. This
   workflow does not add problem-statement context to the existing draft prompt;
   draft prompt text and its hash are kept unchanged.
7. **Scoring and ranking:** explainable hybrid; local embedding/signal outputs
   feed rule-based fit, evidence checks, weighted aggregation, and tiering. See
   the formula and provenance above.
8. **Full product pipeline:** resumable local workflow that sequences profile,
   ICP, per-prospect signals, problem statements, drafts, and final ranking. It
   persists step-level status and resumes queued work after Ollama recovers.

## Offline evaluators

Only `scripts/eval_*.py` and `scripts/validate_corpus.py` read files under
`data/eval/`. The reply evaluator defaults to the 36 development replies and
reports per-label and per-difficulty accuracy, a confusion matrix, and
misclassified reply IDs. Reports under `test_evidence/real_run/` exclude reply
text and rationale. `python scripts/eval_replies.py --freeze-prompt` freezes the
reply prompt hash without inference; a changed hash requires explicit
`--refreeze`. The current baseline is recorded in
`data/eval/frozen_reply_prompt.sha256`. Held-out evaluation uses `--held-out`
and refuses to load its labels or text unless the stored hash matches.
Development runs never read or write the frozen hash.

Signal evaluation has a separate prompt hash and contract. Target a small
development subset with `python scripts/eval_signals.py --model qwen3:4b
--only P012,P028 --verbose`; held-out evaluation is selected explicitly with
`python scripts/eval_signals.py --model qwen3:4b --held-out --verbose` and
requires its own matching `data/eval/frozen_signal_prompt.sha256`. Held-out
signal reports retain run configuration plus IDs and counts only; they exclude
raw replies, evidence, and page text. Local reports and isolated evaluator DBs
are saved under `test_evidence/real_run/`.
