# Changelog

All notable changes to this fork are documented here.

## [Unreleased] — 2026-11-23

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
