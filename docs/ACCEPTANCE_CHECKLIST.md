# Final Acceptance Checklist

## Zero-cost/local proof

- [ ] `make verify` passes; dependency inventory contains no cloud-inference SDKs.
- [ ] `.env.example` contains no keys.
- [ ] During a pipeline run, AI traffic is only to `127.0.0.1:11434` (save evidence).
- [ ] Every inference is visible in the log with model, host, token counts when reported, latency, and timestamp.

## Offline test — Wi-Fi off

- [ ] Business profile generation.
- [ ] Product-specific ICPs (verify two products differ).
- [ ] Prospect research from local data.
- [ ] Buying-signal classification with evidence checks.
- [ ] Grounded problem statements.
- [ ] Personalized email generation (no sending).
- [ ] Deterministic prospect scoring.
- [ ] Reply classification and sample accuracy table.

## Failure handling

- [ ] Stop Ollama: clear error, no remote call, AI task queued, deterministic features continue.
- [ ] Restart Ollama: queued work drains.
- [ ] Missing model: show a helpful pull command.

## Demo outline (~8 minutes)

1. Show installed local models, hardware recommendation, and local status.
2. Create a product; generate its profile and ICP.
3. Load sample prospects and run research.
4. Show verified signals, grounded problem statements, and deterministic scores.
5. Generate a draft email; confirm no send operation exists.
6. Classify sample replies.
7. Inspect inference log and local network connections.
8. Disable Wi-Fi and repeat the local workflow.
9. Stop/restart Ollama and demonstrate queue behavior.

## Submission

- [ ] Public/accessible repository and version tag match the demonstrated code.
- [ ] Docs and test evidence included; mocks and samples are labelled.
