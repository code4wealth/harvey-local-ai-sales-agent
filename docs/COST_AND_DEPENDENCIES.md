# Cost and dependencies

## Cost and network requirements

- **Paid services: none.** The application does not use a paid AI API, hosted
  inference service, or metered enrichment provider.
- **Inference is local only.** Model requests go to the local Ollama service;
  embeddings run from the locally cached sentence-transformer model. There is
  no cloud fallback.
- Internet is needed only to install the project dependencies, obtain/cache
  model files, or conduct fresh web research. The current application uses
  stored-page research and does not fetch new pages itself; once dependencies,
  models, and data are available locally, its workflows can run offline.

## Dependencies

The authoritative dependency declarations and version ranges are in
`pyproject.toml` and `requirements.txt`. The project uses FastAPI, Uvicorn,
HTTPX, Pydantic, Sentence-Transformers, and BeautifulSoup; pytest is a
development dependency. Exact locally observed package versions/licences and
items that remain `not run` are listed in [`LICENSES.md`](LICENSES.md).

BeautifulSoup is used with stored-page research. Scrapy and Playwright are not
used or required by the current application.
