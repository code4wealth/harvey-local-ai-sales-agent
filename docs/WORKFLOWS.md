# Workflows: prompts, schemas, and rules

General rules: keep system instructions short; include a JSON example in the user prompt; use JSON mode; validate with Pydantic; retry invalid JSON at most twice; and log every model call. For Qwen3 send `think: false`. Trim inputs (for example, no more than 3,000 characters of page text per call on small models).

## 1. Business profile

- **Input:** Concatenated `data/company_info/<product>/*.md` files.
- **Schema:** `{summary, value_proposition, key_features[], pain_points_solved[], differentiators[]}`.
- **Rule:** Use only facts in the supplied documents; if a fact is unknown, say `not stated`.

## 2. ICP

- **Input:** Product profile JSON.
- **Schema:** `{industries[], company_size{min,max}, buyer_titles[], pain_points[], trigger_events[], disqualifiers[]}`.
- **Rule:** Make the ICP product-specific and avoid generic filler.

## 3. Prospect research

- **Input:** Locally stored prospect page text (about, careers, news).
- **Schema:** `{what_they_do, size_hint, tech_stack[], recent_news[], summary}`.
- **Similarity:** `icp_similarity = cos_sim(embed(ICP text), embed(prospect text))`; embeddings must be local and are deferred until their library and transitive licenses are reviewed and approved.

## 4. Buying signals

- **Types:** `hiring | funding | expansion | tech_change | leadership_change | pain_mention | none`.
- **Schema:** `{signals:[{type, evidence, confidence}]}` where confidence is between 0 and 1.
- **Code check:** Normalize case and whitespace; `evidence` must be a substring of the source. Drop unverified signals.
- **Score:** Sum `weight[type] * confidence`, capped at 100. Initial tunable weights: funding 30, hiring 25, expansion 20, pain_mention 25, leadership_change 15, tech_change 15.

## 5. Problem statement

- **Input:** Product profile, research summary, verified signals.
- **Output:** Two or three sentences; no invented facts; mention the supporting signal.

## 6. Scoring — no model

```text
0.35 * similarity * 100 + 0.35 * signal_score + 0.15 * size_fit + 0.15 * title_fit
```

Size fit is 100 in the ICP range with linear decay outside; title fit is a deterministic fuzzy match against ICP buyer titles. Persist the score breakdown. An optional one-line model rationale is skipped if Ollama is down; the score itself never changes.

## 7. Email generation — never send

- **Input:** Product profile, research, verified signals, problem statement, contact name/title.
- **Output:** `{subject, body}`.
- **Rules:** Fewer than 120 words, one call to action, no fake claims/statistics/customers, reference one real signal, plain tone, and no generic well-wishing opener.
- **Code check:** Count words and regenerate once if over the limit. This workflow only drafts text; it does not send email.

## 8. Reply classification

- **Labels:** `interested | meeting_request | not_interested | out_of_office | wrong_person | unsubscribe | question | other`.
- **Schema:** `{label, confidence, next_action}`.
- **Evaluation:** Run against labelled `data/sample_replies.json`; `scripts/eval_replies.py` reports accuracy and a confusion table to `test_evidence/`.
- **Safety:** An unsubscribe must be honoured by flagging the prospect as do-not-contact.

## Pipeline

`POST /api/pipeline/run/{product_id}` runs profile → ICP → per-prospect research → signals → problem → score → email. Persist each step's status; make runs product-scoped, resumable, and safe to retry. Reply classification is an independent workflow.
