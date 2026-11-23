Workflows: prompts, schemas, rules
General: keep the system prompt short; pass the Pydantic JSON schema in Ollama's `format`; validate with Pydantic; retry invalid JSON ×2; log every call.
Qwen3: think:false, temperature 0.2. Keep source text to roughly <=2500 tokens per call; pass the hardware tier's recommended `num_ctx` (default 4096).
1. Business profile
Input: concatenated data/company_info/<product>/*.md.
Schema: {summary, value_proposition, key_features[], pain_points_solved[], differentiators[]}.
Rule: use only facts present in the documents; if unknown, say "not stated".
2. ICP
Input: profile JSON. Schema: {industries[], company_size{min,max}, buyer_titles[], pain_points[], trigger_events[], disqualifiers[]}.
Rule: must be product-specific; avoid generic output.
3. Prospect research
Input: prospect page text (about/careers/news). Schema: {what_they_do, size_hint, tech_stack[], recent_news[], summary}.
Plus: icp_similarity = cos_sim(embed(ICP text), embed(prospect text)).
4. Buying signals
Types: hiring | funding | expansion | tech_change | leadership_change | pain_mention | none.
Schema: {signals:[{type, evidence, confidence 0-1}]}.
Code check: evidence must be a substring (case/whitespace-normalised) of the source; otherwise drop. Signal score = sum weight[type]*confidence, capped at 100.
Weights (tunable): funding 30, hiring 25, expansion 20, pain_mention 25, leadership_change 15, tech_change 15.
5. Problem statement
Input: profile, research summary, verified signals. Output: 2-3 sentences, no invented facts, mentions the signal.
6. Scoring (no LLM)
0.35*sim*100 + 0.35*signal_score + 0.15*size_fit + 0.15*title_fit. size_fit: 100 in ICP range, linear decay outside. title_fit: fuzzy match to ICP buyer_titles.
Store breakdown JSON. Optional LLM one-line rationale (skipped if Ollama down).
7. Email
Input: profile, research, signals, problem, contact name/title. Output {subject, body}.
Rules: <120 words, one CTA, no fake claims/stats/customers, reference one real signal, plain tone, no "I hope this finds you well".
Post-check in code: word count; regenerate once if over.
8. Reply classification
Labels: interested | meeting_request | not_interested | out_of_office | wrong_person | unsubscribe | question | other.
Schema: {label, confidence, next_action}. Run over data/sample_replies.json; scripts/eval_replies.py outputs accuracy + confusion table to test_evidence/.
unsubscribe must be honoured: prospect flagged do-not-contact.
9. Pipeline
POST /api/pipeline/run/{product_id}: profile -> ICP -> for each prospect (research -> signals -> problem -> score -> email). Per-step status, resumable, safe to re-run.
