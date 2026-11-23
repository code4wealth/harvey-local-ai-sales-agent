# PRD — Harvey Local Multi-Product AI Sales Agent

## 1. Objective

Build a multi-product sales agent that runs its AI workflows locally with zero LLM cost using Ollama, SQLite, Python, FastAPI, a local dashboard, and optional public-web research. AI inference must work offline after the local model is downloaded.

## 2. Hard constraints

- No hosted or paid LLM API, cloud inference, paid agent platform, paid enrichment API, or per-token service.
- No silent fallback. If Ollama is down, report a clear error and queue AI work; deterministic features remain available.
- After installation and model download, AI workflows must run with the internet disconnected.
- External web research is optional and separated from local AI inference.
- Never present hard-coded output as generated intelligence. All mock and sample data must be clearly labelled.
- Secrets stay outside source control; no AI keys are used.
- Do not implement actual email sending, CRM integration, paid research, or trainer default values.

## 3. User and value

The primary user is a founder or SDR selling several products who needs product-specific ICPs, prospect research, signals, scoring, and outreach while keeping inference private and free on a laptop.

## 4. Functional requirements

| ID | Requirement | Acceptance |
|---|---|---|
| F1 | Multi-product company configuration | Create, edit, and list products; keep company documents local and product-specific |
| F2 | Business profile generation | Generate and persist a validated profile from local company information |
| F3 | Product-specific ICP | Different products produce distinct validated ICPs |
| F4 | Prospect import and local page data | Import CSV and use local pages; online research is optional and isolated |
| F5 | Prospect research | Summarize downloaded page data and calculate local embedding similarity |
| F6 | Buying-signal classification | Typed signals include verified evidence quotes and confidence |
| F7 | Problem statement | Two or three sentences grounded in the profile, research, and verified signals |
| F8 | Prospect scoring | Deterministic hybrid score, persisted breakdown, sorted results |
| F9 | Personalized email generation | Fewer than 120 words, one CTA, no invented facts; generation only, never send |
| F10 | Reply classification | Eight labels, confidence, next action, and evaluation on labelled samples |
| F11 | Hardware recommendation | Detect RAM, CPU, and available GPU information and recommend a model tier |
| F12 | Failure handling | Clear Ollama status, retryable AI queue, and working deterministic features |
| F13 | Traceability | Inference log records model, host, token counts, latency, timestamp, and outcome |
| F14 | Product pipeline | Run product workflows with per-step status and safe resume/retry |

## 5. Non-functional requirements

- Reliability: validate JSON, retry invalid model output at most twice, handle timeouts, and report failures clearly.
- Reproducibility: one setup path and consistent dependency manifests.
- Privacy: no telemetry; AI network traffic is limited to `127.0.0.1:11434`.
- Performance: the laptop tier targets `qwen3:4b`; show pipeline progress and per-step status.
- Licensing: document exact licenses for models, libraries, and major dependencies before release.

## 6. Hardware tiers

| Tier | Condition | Suggested model |
|---|---|---|
| High-performance | VRAM ≥ 12 GB or RAM ≥ 32 GB | `qwen3:14b` |
| Standard-plus | VRAM ≥ 6 GB or RAM ≥ 16 GB | `qwen3:8b` |
| Standard laptop | RAM > 8 GB | `qwen3:4b` |
| Low-resource | Otherwise | `qwen3:1.7b` |

## 7. Sample data

The planned `data/` tree contains only clearly labelled sample company documents, prospects, prospect page text, and labelled replies. Do not commit real prospect data or present invented records as research.

## 8. Deterministic scoring

```text
score = 0.35 * icp_similarity * 100
      + 0.35 * signal_score
      + 0.15 * size_fit
      + 0.15 * title_fit
```

Store a component breakdown. Size fit is 100 in the ICP range and decays linearly outside it; title fit is a deterministic fuzzy match. A model may add a one-line rationale, but never changes the numeric score. All deterministic features continue to work when Ollama is unavailable.
