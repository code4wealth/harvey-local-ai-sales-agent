from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def test_offline_make_target_runs_verification_with_both_model_caches_offline():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    environment = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "OFFLINE_STRICT=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 $(MAKE) verify" in makefile
    assert "scripts/offline_test.py" not in makefile
    assert "HF_HUB_OFFLINE=1" in environment
    assert "TRANSFORMERS_OFFLINE=1" in environment
    assert "OFFLINE_STRICT=1" in environment


@pytest.mark.parametrize(
    ("name", "evidence_path"),
    [
        ("offline_acceptance.ps1", '"test_evidence\\offline"'),
        ("ollama_down_check.ps1", '"test_evidence\\ollama_outage"'),
    ],
)
def test_power_shell_acceptance_scripts_are_loopback_only_and_text_free(name, evidence_path):
    source = (SCRIPTS / name).read_text(encoding="utf-8")

    assert '"http://127.0.0.1:8000"' in source
    assert "$handler.UseProxy = $false" in source
    assert "$handler.AllowAutoRedirect = $false" in source
    assert evidence_path in source
    assert "ConvertTo-Json" in source
    assert "Write-Host \"[$result] $Name\"" in source
    assert "Invoke-WebRequest" not in source
    assert "Invoke-RestMethod" not in source
    assert "Get-Content" not in source
    assert re.search(r"\bpip\b|\bgit\b|\bcurl\b", source, re.IGNORECASE) is None

    urls = re.findall(r"https?://[^\s\"'`]+", source, re.IGNORECASE)
    for value in urls:
        parsed = urlsplit(value)
        assert parsed.scheme == "http"
        assert parsed.hostname in {"127.0.0.1", "::1"}


def test_offline_acceptance_covers_the_eight_workflows_including_pipeline():
    source = (SCRIPTS / "offline_acceptance.ps1").read_text(encoding="utf-8")

    for workflow in (
        "Business profile product",
        "ICP product",
        "Signals for stored-page prospects",
        "Deterministic ranking product",
        "Unsent draft",
        "Problem statements (IDs, statuses, counts only)",
        "Reply classification",
        "Full product pipeline",
    ):
        assert workflow in source
    assert '"/api/products/$ProductId/pipeline"' in source
    assert '"/api/pipeline-runs/$runId"' in source
    assert "-TimeoutSeconds $PipelineWaitSeconds" in source


def test_ollama_outage_script_guides_stop_queue_restart_and_retry():
    source = (SCRIPTS / "ollama_down_check.ps1").read_text(encoding="utf-8")

    assert "Stop the local Ollama service/model now" in source
    assert '"/api/prospects/$prospectId/signals"' in source
    assert '$queuedState -eq "queued"' in source
    assert "Start the local Ollama service/model now" in source
    assert '"/api/queue/retry"' in source
    assert "Queued workflow retry result" in source
    assert '"test_evidence\\ollama_outage"' in source
