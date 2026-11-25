# Changelog

All notable changes to this fork are documented here.

## [Unreleased] — 2026-11-23

- Resolve backend model preferences against Ollama's installed tags before
  inference; expose model inventory, selection source, embedding-cache state,
  and combined local readiness. Model-tag outages queue workflows without
  attempting `/api/chat`.
- Removed browser-side model selection and made the diagnostics, dashboard, and
  settings report installed models, the actual embedding model/cache, and live
  readiness instead of implying an unverified model is ready.
- Changed the draft prompt's formatting example to a deterministic synthetic
  placeholder that cannot pass the existing evidence checks; evidence
  validation remains strict.
- Clarified simulated-offline status across model settings, dashboard, and
  activity views; a UI-only override now says it is simulated and performs no
  inference instead of implying a real network/Ollama outage.
- Added project status and submission notes with distinct owner-reported versus
  workspace-verified results, actual evidence-file inventory, and official
  model/runtime/Windows-package licence pages. Missing logs, screenshots, video
  URL, footer hash, and outage result remain explicitly pending; the owner has
  confirmed the reported run-date field, but the future-dated run outcomes are
  still unsupported by target-run evidence in this checkout.
- Expanded the README opening with six local-run/offline steps, failure
  handling, and the mocked-test limitation.
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
