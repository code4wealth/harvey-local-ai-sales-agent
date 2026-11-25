.PHONY: verify test run offline

verify:
	python scripts/verify_no_cloud.py
	python scripts/validate_corpus.py
	pytest -q

test:
	pytest -q

run:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

offline:
	OFFLINE_STRICT=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 $(MAKE) verify
