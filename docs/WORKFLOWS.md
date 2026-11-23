# Workflows and scoring contracts

This document separates implemented deterministic behavior from LLM workflows
that have **not** been started. No workflow prompts are being tuned in this
patch; the operator will tune them against real local-model output later.

## Implemented deterministic batch

### Products and prospects

- Products are stored locally in SQLite with a name, description, and local
  documentation path. A product owns its prospects.
- CSV import is product-scoped. Headers are case-insensitive; spaces and
  hyphens normalize to underscores. `company_name` is required. Supported
  optional headers are `contact_name`, `contact_title`, `company_domain`,
  `employee_count`, `contact_email`, `page_text_path`, and `do_not_contact`.
  Imports validate before writing and are atomic.
- `page_text_path` is a filename or path inside `data/prospect_pages/`. Page
  text is explicitly stored/read as local UTF-8 text. Replacing it clears the
  cached page embedding. The API does not fetch a URL or perform online research.
- Queue handlers `prospects.import_csv` and `prospects.score` are
  **deterministic** and do not require an Ollama health probe. A slow or
  unavailable probe must not block these local tasks. LLM-dependent handlers
  still wait for Ollama. The score handler embeds persisted flat ICP JSON and
  local page text when their vectors are absent, stores local vectors, then
  scores. If a required vector cannot be computed or loaded, similarity stays
  null and the result is partial.

### Local embeddings

- `app/embeddings.py` uses the real
  `sentence-transformers/all-MiniLM-L6-v2` model and returns normalized local
  vectors. The model is lazy-loaded and cached in-process. Test doubles exist
  only in `tests/`.
- First run `python scripts/smoke_embeddings.py` while the model can be
  downloaded. After the model is cached, run with `HF_HUB_OFFLINE=1` to check
  offline load and inference. On Windows PowerShell use
  `$env:HF_HUB_OFFLINE='1'; python scripts/smoke_embeddings.py`; in Command
  Prompt use `set HF_HUB_OFFLINE=1 && python scripts/smoke_embeddings.py`.
  No embedding output is fabricated when the model is absent.

## Quote verification — deterministic

Before checking evidence quotes, normalize both source and candidate quote in
this order:

1. Unicode NFKC normalization.
2. Straighten curly single/double quotes and common Unicode dashes to straight
   ASCII quote characters and hyphens.
3. Collapse every whitespace run to one space and trim.
4. Lowercase.

Retain a quote only if its **normalized** text is a substring of the
**normalized** source. Return the retained normalized quotes and the count
that were dropped. Non-string, empty, and unmatched quotes are dropped; a
quote is never repaired by inventing source text.

## Scoring — deterministic

### ICP similarity

Compute cosine similarity between the local ICP and prospect embeddings, then
map it linearly from cosine `0.15 → 0` to `0.65 → 1`; clamp below and above
that interval to `0` and `1`. Missing, mismatched, or zero-length vectors make
the component `null`.

### Signal score

Each signal type contributes at most once, using the highest valid confidence
for that type. The contribution is `weight × confidence`; the total is capped
at 100. The existing baseline weights are:

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

### Size fit

Use the ICP's flat `company_size_min` and `company_size_max` fields and the
prospect's recorded `employee_count`. Fit is 100 inside the inclusive range.
Outside it, let `r` be the ratio to the nearest boundary (`employees / max`
above the range, `min / employees` below it). Fit decays logarithmically as
`100 × (1 − ln(r) / ln(3))`, reaching zero at a 3× ratio. Missing or invalid
inputs make the component `null`.

### Title fit

Use only the ICP's `buyer_titles` keywords. A buyer-title phrase appearing
contiguously in the contact title scores 100 (decision-maker); any remaining
non-connector keyword overlap scores 60 (influencer); no overlap scores 20
(other). If the contact title or buyer-title list is missing, the component
is `null`. No external title dictionary or synonym list is inferred.

### Overall score and missing inputs

The complete formula is:

`0.35 × icp_similarity × 100 + 0.35 × signal_score + 0.15 × size_fit + 0.15 × title_fit`

`icp_similarity` is on 0–1; the other components are on 0–100. An
uncomputable component is stored as JSON `null`, and `partial` is true. The
partial total sums only known weighted contributions using the original
weights (no re-normalization); it is not presented as a complete score. If
all components are missing, `score` is `null`. Never substitute guessed
inputs, zero-fill missing metrics, or claim a partial total is complete.

## LLM workflow contract — deferred; no prompts implemented here

When these workflows are started, every schema-constrained LLM output must be
flat: scalar fields at the root, with lists of scalars or lists of flat
objects at most. Do not use nested objects. Validate structured output and
keep the existing local-only `app/llm_client.py` path; no workflow may call a
model or service directly.

Planned inputs/outputs (contract only; all marked **not started**):

1. **Business profile — not started:** local product documents; flat summary,
   value proposition, and lists of features, pain points, and differentiators.
2. **ICP — not started:** business profile; flat industry/title/event lists
   and `company_size_min` / `company_size_max` fields.
3. **Prospect research — not started:** explicitly stored local page text; flat
   summary/size fields and lists for technology and news. Embeddings remain a
   separate local deterministic operation.
4. **Buying signals — not started:** local page text; `{signals: [...]}` where
   each signal is a flat `{type, evidence, confidence}` object. Apply the
   deterministic quote verification above before storing evidence.
5. **Problem statement — not started:** profile, research, and verified
   signals; 2–3 factual sentences, with no invented inputs.
6. **Scoring — deterministic implementation exists:** use the formula and
   component rules above; it does not need an LLM rationale.
7. **Email — not started:** flat `{subject, body}` output; later enforce the
   existing length, one-call-to-action, and no-fabricated-claims rules.
8. **Reply classification — not started:** flat `{label, confidence,
   next_action}` output and honour unsubscribe/do-not-contact.
9. **Pipeline orchestration — not started:** workflow sequencing and resumable
   LLM stages are intentionally deferred.
