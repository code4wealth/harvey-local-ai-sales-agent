# Cost and dependencies

## Cost and network requirements

- **Paid service/API cost: $0.** The application does not use a paid AI API,
  hosted inference service, or metered enrichment provider. Local hardware,
  electricity, and one-time model-download bandwidth are user-provided resources
  and are not monetized or estimated by this project.
- **Inference is local only.** Model requests go to the local Ollama service;
  embeddings run from the locally cached sentence-transformer model. There is
  no cloud fallback.
- Internet is needed to install dependencies, obtain/cache model files, or
  when an operator explicitly runs the separate online helper
  `scripts/fetch_public_pages.py`. The FastAPI application itself uses only
  stored-page research and does not fetch new pages. Once dependencies, models,
  and data are available locally, its workflows can run offline; the optional
  page-collection helper cannot.

## Dependencies

The authoritative dependency declarations and version ranges are in
`pyproject.toml` and `requirements.txt`. The project uses FastAPI, Uvicorn,
HTTPX, Pydantic, Sentence-Transformers, BeautifulSoup, and Requests. Requests
and BeautifulSoup support the separately invoked, optional online collector;
they are not used by the FastAPI inference path. Pytest is a development
dependency. Exact locally observed package versions/licences and items that
remain `not run` are listed in [`LICENSES.md`](LICENSES.md).

Stored-page workflows require no web fetcher. Scrapy and Playwright are not
installed or used by this project.
