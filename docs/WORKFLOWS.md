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
  embedding. The API does not fetch a URL or perform online research.
- Queue handlers `prospects.import_csv` and `prospects.score` are
  **deterministic** and do not require an Ollama health probe. A slow or
  unavailable probe must not block these local tasks. LLM-dependent handlers
  still wait for Ollama. The score handler embeds persisted flat ICP JSON and
  local page text when their vectors are absent, stores local vectors, then
  scores. If a required vector cannot be computed or loaded, similarity stays
  null and the result is partial.

### Local embeddings

- `app/embeddings.py` uses the
  `sentence-transformers/all-MiniLM-L6-v2` model and returns normalized local
  vectors. The model is lazy-loaded and cached in-process. Test doubles exist
  only in `tests/`.
- MiniLM-L6 has a `max_seq_length` of 256 word pieces and silently truncates
  longer inputs. `embed_long_text` splits page text on whitespace into chunks
  of about 800 characters, embeds at most six chunks, averages their vectors,
  and renormalizes the result. Text beyond six chunks is omitted.
- First run `python scripts/smoke_embeddings.py` while the model can be
  downloaded; it reports `max_seq_length` and vector dimension. After the model
  is cached, run with `HF_HUB_OFFLINE=1` to check offline load and inference.
  Set offline variables in the shell before starting Python (before importing
  the embeddings library). On Windows PowerShell use
  `$env:HF_HUB_OFFLINE='1'; python scripts/smoke_embeddings.py`; in Command
  Prompt use `set HF_HUB_OFFLINE=1 && python scripts/smoke_embeddings.py`.
  Failed model loads are not cached, so a later call will try loading again.
  No embedding output is fabricated when the model is absent.

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
including `none`, are dropped and counted separately from evidence failures.

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

Use only the ICP's `buyer_titles` keywords. A substantive buyer-title phrase
appearing contiguously in the contact title scores 100 (decision-maker); any
remaining non-connector keyword overlap scores 60 (influencer); no substantive
overlap scores 20 (other). Seniority-only overlap (`vp`, `director`, `head`, `manager`,
`chief`, `senior`, `lead`) is not substantive. Contact-title modifiers
(`intern`, `assistant`, `associate`, `junior`, `former`, `ex`, `student`) cap
the score at 20. If the contact title or buyer-title list is missing, the
component is `null`. This remains a deterministic keyword heuristic; see
`docs/KNOWN_LIMITATIONS.md`.

### Overall score and missing inputs

The complete formula is:

`0.35 × icp_similarity × 100 + 0.35 × signal_score + 0.15 × size_fit + 0.15 × title_fit`

`icp_similarity` is on 0–1; the other components are on 0–100. An
uncomputable component stays JSON `null`, contributes zero to the weighted
sum, appears in `missing_components`, and sets `partial` true. Use the original
weights without re-normalization. If all components are missing, the score is
`0` and `partial` is true. Never substitute guessed inputs or claim a partial
total is complete.

## LLM workflow status

All inference uses the local `app/llm_client.py` path. Structured outputs are
Pydantic-validated and retried at most twice; workflow-specific grounding
validators participate in those same three total attempts. No workflow calls
a model or service directly.

Implemented:

1. **Business profile:** local company-info document; summary, value
   proposition, key features, pain points solved, differentiators,
   `typical_buyer`, `typical_team_size`, `working_situation`, and `not_for`.
   General claims need 60% normalized content-word overlap with the source;
   each pain-point item needs 80%. Missing fields on previously saved profiles
   are supplied as `not stated` for ICP generation without rewriting the
   stored profile.
2. **ICP:** uses the stored profile's buyer, team-size, working-situation,
   pain-point, and `not_for` fields. Every list item is grounded in its
   field-specific profile support; unsupported lists may be empty or contain
   `not stated`; numeric size bounds require explicit numeric support. A
   trigger must describe a concrete external event, not a product feature.
3. **Buying signals:** local prospect page; `{signals: [...]}` where each
   item is `{type, evidence, about_company}`. Evidence is checked against the
   source and filtered for unrelated-company, negated, and stale events before
   persistence.
4. **Scoring — deterministic implementation exists:** use the formula and
   component rules above; it does not need an LLM rationale.

Prospect research, problem statements, email generation, reply classification,
and full pipeline orchestration are not implemented in this workflow batch.
Signal evaluation is separate from runtime: only offline `scripts/eval_*.py`
and `scripts/validate_corpus.py` may read files under `data/eval/`. Target a
small development subset with `python scripts/eval_signals.py --model qwen3:4b
--only P012,P028 --verbose`; run the reserved set with
`python scripts/eval_signals.py --model qwen3:4b --held-out --verbose`.
`--freeze-prompt` checks (and, if absent, initializes) the prompt baseline;
held-out always enforces it. Local reports and the isolated evaluator DB are
saved under `test_evidence/real_run/`.
