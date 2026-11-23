# SAMPLE data corpus

Every corpus artifact in this directory is fictional and marked `SAMPLE` in its contents, record labels, or product-import CSV filename. It is for offline tests only and is not real company research or generated intelligence.

- `company_info/relaycue.md` and `company_info/fieldnest.md`: two distinct fictional products.
- `prospects/SAMPLE_relaycue.csv` and `prospects/SAMPLE_fieldnest.csv`: 21 and 20 fictional product-prospect rows. Each file uses exactly the fields in `app.prospects.CSV_FIELDS` and is directly importable for its product. `page_text_path` is repository-root-relative (for example, `data/prospect_pages/p001.txt`); the page filename links to `prospect_id` in `eval/sample_case_notes.csv`.
- `prospect_pages/`: 37 imported prospect source pages plus 12 additional held-out signal pages, all fictional. Product-import CSV rows use reserved `.example` domains; the extra signal pages P038-P049 are evaluator inputs, not product-import rows.
- `sample/replies.csv`: exactly 60 fictional reply IDs and texts; its only columns are `reply_id,text`. It deliberately contains no label, difficulty, or split annotations.
- `sample/reply_labels.csv`: optional operator-authored ground truth. It is not included by default and must not be fabricated or edited by tooling. If present, the validator checks IDs and allowed labels; otherwise it prints `reply_labels.csv not present yet` and passes.
- `eval/sample_case_notes.csv` and `eval/expected_signals.csv`: evaluator-only annotations for the 37 imported prospect sources. Do not pass these files to a workflow as prospect evidence.
- `eval/signal_holdout/expected.csv`: expected signal types and trap cases for P038-P049. The associated pages are in `prospect_pages/` so the normal local-page workflow can process them, while expected labels remain under `eval/`.

The signal holdout includes funding, hiring, expansion, technology change, leadership change, pain mentions, a multi-signal page, no-signal and implied/no-signal cases, a negated event, a stale announcement, and a third-party event. Signal ground truth is read only by offline evaluator/validator scripts.
