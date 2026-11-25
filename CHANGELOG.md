# Changelog

All notable changes to this fork are documented here.

## [Unreleased] — 2026-11-23

- Improved draft and problem-statement prompts for specific, evidence-grounded
  outreach and cautious operational interpretations; existing evidence and
  anti-fabrication validators were not loosened.
- Corrected README/demo/operations documentation, documented the optional
  explicit-URL Requests + BeautifulSoup collector design, and reconciled
  sandbox package licence metadata with unresolved target/model checks.
- Added Windows offline/outage demo instructions and an online screenshot-notes
  template. Physical laptop, Wi-Fi-off, live Ollama, CPU/GPU placement, and
  screenshot results remain **PENDING**; no evidence was fabricated.
- Corrected the embedding smoke-script instructions: populate the cache directly
  before using the app's forced-offline loader.
- Conversion of the upstream Harvey/Sellbird codebase (base commit
  `b2123852`) into a fully local, zero-LLM-cost, multi-product AI sales agent
  (EDXSO AI Engineer Intern — Assignment 2).
- Removed the upstream subscription-CLI architecture and every cloud-AI
  reference; all AI inference now goes through a single local Ollama client.
- New dependency set (FastAPI, httpx, pydantic, sentence-transformers,
  beautifulsoup4); licence table in docs/.
- Added `scripts/verify_no_cloud.py` zero-cloud guard, `Makefile`, pack docs
  (PRD, ARCHITECTURE, WORKFLOWS, TASKS, ACCEPTANCE_CHECKLIST).
- Recon recorded in docs/HARVEY_NOTES.md.
