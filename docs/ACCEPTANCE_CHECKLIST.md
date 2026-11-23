Final Acceptance Checklist
Zero-cost proof
[ ] make verify green; pip freeze has no cloud-AI SDKs
[ ] .env.example has no keys
[ ] During pipeline run, only 127.0.0.1:11434 for AI traffic (screenshot)
[ ] Inference log shows model, host, tokens, latency for every call
Offline test (Wi-Fi OFF, visibly)
[ ] Business profile
[ ] Product-specific ICP (two products differ)
[ ] Prospect research from local data
[ ] Buying-signal classification
[ ] Problem statements
[ ] Personalised emails
[ ] Prospect scoring
[ ] Reply classification (+ accuracy table)
Failure handling
[ ] Stop Ollama -> clear error, no cloud call, task queued, deterministic features work
[ ] Restart Ollama -> queue drains
[ ] Model not pulled -> helpful message
Demo video script (~8 min)
1. ollama list, hardware recommendation, status bar (0:30)
2. Create product -> profile -> ICP (1:00)
3. Import prospects, research (1:00)
4. Signals, problems, scores (1:30)
5. Emails (1:00)
6. Reply classification (1:00)
7. Inference log + network check (0:45)
8. Wi-Fi off -> repeat pipeline (2:00)
9. Stop/start Ollama -> queue demo (0:30)
Submission
[ ] Repo public/accessible, tag v1.0 matches video
[ ] Docs + test_evidence included; mocks/samples labelled
