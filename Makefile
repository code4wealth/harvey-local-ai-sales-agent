.PHONY: verify test run offline
verify:
	python scripts/verify_no_cloud.py
	python scripts/validate_corpus.py
	pytest -q

test:
	pytest -q

run:
	uvicorn app.main:app --reload

offline:
	HF_HUB_OFFLINE=1 python scripts/offline_test.py
