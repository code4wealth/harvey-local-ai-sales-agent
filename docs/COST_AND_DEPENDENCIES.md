# Cost and dependencies

## Cost and network requirements

- **Paid service/API cost: $0.** The application does not use a paid AI API,
  hosted inference service, or metered enrichment provider. Local hardware,
  electricity, and one-time model-download bandwidth are user-provided resources
  and are not monetized or estimated by this project.
- **Inference is local only.** Structured JSON workflows send a Pydantic JSON
  schema to the Ollama service on loopback and set `think=false`; there is no
  cloud fallback. Requests use a 300-second timeout by default. Set
  `OLLAMA_TIMEOUT_SECONDS` to a positive number of seconds to change it.
- Embeddings use the locally cached `sentence-transformers/all-MiniLM-L6-v2`
  model. Model weights are not vendored; cache them before an offline run.
- Internet is needed to install Python dependencies, obtain/cache Ollama and
  embedding model files, or when an operator explicitly runs the separate
  online helper `scripts/fetch_public_pages.py`. That helper reads explicit
  public URLs from a CSV. The FastAPI application itself uses only local stored
  page text and does not fetch new pages. Once dependencies, models, and data
  are available locally, its workflows can run offline; the optional page
  collector cannot.
- Importing `data/sample/replies.csv` through `POST /api/replies/import-sample`
  is local and idempotent; it does not add a paid service or send the reply text
  to a hosted endpoint.

## Dependencies

The authoritative Python package declarations and version ranges are in
`pyproject.toml` and `requirements.txt`. Runtime packages are FastAPI, Uvicorn,
HTTPX, Pydantic, Sentence-Transformers, BeautifulSoup, and Requests. The
Sentence-Transformers package and its model are separate artifacts; check both
before redistribution. Requests and BeautifulSoup support the separately
invoked optional public-page collector and stored-page text parsing; neither
connects the inference path to a hosted AI service. Pytest is a development
dependency. Ollama is a separate local runtime, not a Python package dependency.

Stored-page workflows require no web fetcher. **Scrapy and Playwright are not
installed or used** by this project; it does not crawl or automate a browser.

## Public-page collector design decision

`scripts/fetch_public_pages.py` uses the already-declared Requests client for
bounded, explicit HTTP requests and BeautifulSoup for deterministic parsing of
HTML already returned by those requests. The helper reads a CSV `url` column;
it does not discover or follow page links. It requests each listed page, checks
that origin's `robots.txt`, and follows only bounded redirects needed for that
listed page. It has time, size, redirect, host-delay, and public-address
checks. This is a small, operator-invoked collection task, so Scrapy's crawl
scheduler and Playwright's JavaScript-capable browser automation would add
unneeded machinery and dependencies; browser rendering and broad crawling are
out of scope. The collector is an **ONLINE, separate utility**, never called by
the FastAPI AI workflows. Collected text must be reviewed and imported as local
page text before those offline workflows can use it. No dependency was added
for this design.

Observed package metadata and unresolved licence/version items are recorded in
[`MODELS_AND_LICENCES.md`](MODELS_AND_LICENCES.md). Items not confirmed for the
target Windows environment or exact model artifact are marked `VERIFY`; the
sandbox observations are not a Windows dependency lockfile or legal opinion.
