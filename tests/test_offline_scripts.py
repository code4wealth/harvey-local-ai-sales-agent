from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POWERSHELL_SCRIPTS = ("offline_acceptance.ps1", "ollama_down_check.ps1")
REQUIRED_WORKFLOW_ORDER = (
    "1. Business profile",
    "2. Product ICP",
    "3. Research from saved prospect data",
    "4. Signals",
    "5. Problem statement",
    "6. Scoring/ranking",
    "7. Unsent email draft",
    "8. Reply classification",
)


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
        (
            "offline_acceptance.ps1",
            'Join-Path (Join-Path $script:RepoRoot "test_evidence") "offline"',
        ),
        (
            "ollama_down_check.ps1",
            'Join-Path (Join-Path $script:RepoRoot "test_evidence") "ollama_outage"',
        ),
    ],
)
def test_power_shell_acceptance_scripts_are_loopback_only_and_text_free(name, evidence_path):
    source = (SCRIPTS / name).read_text(encoding="utf-8")

    assert '"http://127.0.0.1:8000"' in source
    assert "$script:ApiHandler.UseProxy = $false" in source
    assert "$script:ApiHandler.AllowAutoRedirect = $false" in source
    assert evidence_path in source
    assert "ConvertTo-Json" in source
    assert "Write-Host $Message" in source
    assert "Invoke-WebRequest" not in source
    assert "Invoke-RestMethod" not in source
    assert "Get-Content" not in source
    assert re.search(r"\bpip\b|\bgit\b|\bcurl\b", source, re.IGNORECASE) is None

    urls = re.findall(r"https?://[^\s\"'`]+", source, re.IGNORECASE)
    public_host_urls = [url for url in urls if urlsplit(url).hostname == "example.com"]
    if name == "offline_acceptance.ps1":
        assert public_host_urls == ["https://example.com/"]
    else:
        assert public_host_urls == []

    for value in urls:
        parsed = urlsplit(value)
        if parsed.hostname == "example.com":
            assert name == "offline_acceptance.ps1"
            assert parsed.scheme == "https"
        else:
            assert parsed.scheme == "http"
            assert parsed.hostname in {"127.0.0.1", "::1"}


@pytest.mark.parametrize("name", POWERSHELL_SCRIPTS)
def test_powershell_scripts_parse_without_syntax_errors(name):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail("PowerShell is required in CI to run the PowerShell Parser syntax check")
        pytest.skip("PowerShell is not installed; CI requires it for the Parser syntax check")

    script_path = str((SCRIPTS / name).resolve()).replace("'", "''")
    parser_command = (
        "$tokens = $null; $parseErrors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script_path}', [ref]$tokens, [ref]$parseErrors); "
        "if ($parseErrors.Count -gt 0) { "
        "$parseErrors | ForEach-Object { [Console]::Error.WriteLine("
        "('{0}:{1}: {2}' -f $_.Extent.StartLineNumber, "
        "$_.Extent.StartColumnNumber, $_.Message)) }; exit 1 }"
    )
    result = subprocess.run(
        [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", parser_command],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_offline_acceptance_records_workflows_in_the_required_order():
    source = (SCRIPTS / "offline_acceptance.ps1").read_text(encoding="utf-8")

    workflow_calls = re.findall(r'^\s*Run-WorkflowStep "([^"]+)"', source, re.MULTILINE)
    assert tuple(workflow_calls) == REQUIRED_WORKFLOW_ORDER

    metadata = re.search(r"workflow_order = @\((.*?)\n    \)", source, re.DOTALL)
    assert metadata is not None
    assert tuple(re.findall(r'"([^"]+)"', metadata.group(1))) == REQUIRED_WORKFLOW_ORDER

    assert "Full product pipeline (extra)" not in source
    assert "/api/products/$ProductId/pipeline" not in source
    assert "/api/pipeline-runs/$runId" not in source


def test_offline_acceptance_loads_saved_page_without_a_model_call_and_probes_first():
    source = (SCRIPTS / "offline_acceptance.ps1").read_text(encoding="utf-8")

    assert '$script:InternetProbe = Test-PublicInternet' in source
    assert source.index('$script:InternetProbe = Test-PublicInternet') < source.index(
        '$statusResponse = Invoke-LocalApi -Method "GET" -Path "/api/status"'
    )
    assert '"https://example.com/"' in source
    assert "request_failed = $false" in source
    assert "request_failed = $true" in source
    assert "This run is NOT an offline proof." in source
    assert 'Get-SavedPageMetadata -RelativePath $relativePagePath' in source
    assert '$text = [IO.File]::ReadAllText($fullPath, [Text.Encoding]::UTF8)' in source
    assert "file_path = $page.FilePath" in source
    assert "character_count = $page.CharacterCount" in source
    assert "model_call = $false" in source


def test_ollama_outage_script_guides_stop_queue_restart_and_retry_and_records_evidence():
    source = (SCRIPTS / "ollama_down_check.ps1").read_text(encoding="utf-8")

    assert "Stop the local Ollama service/model now" in source
    assert '"/api/prospects/$prospectId/signals"' in source
    assert '$queuedState -eq "queued"' in source
    assert "Get-ErrorClass $queuedPayload.error" in source
    assert "Start the local Ollama service/model now" in source
    assert '"/api/queue/retry"' in source
    assert "Queued workflow retry result" in source
    assert 'Join-Path (Join-Path $script:RepoRoot "test_evidence") "ollama_outage"' in source
    assert '"ollama-down-$($script:RunStamp).log"' in source
    assert '"ollama-down-$($script:RunStamp).json"' in source
    assert "commit_hash = $null" in source
    assert "ollama_host = \"127.0.0.1\"" in source
    assert "ollama_version = $null" in source
    assert "seed = $null" in source
    assert "temperature = $null" in source
    assert '$script:Evidence["steps"]' in source
    assert '$script:Evidence["overall_result"]' in source
    assert 'Set-Content -LiteralPath $script:JsonPath -Encoding UTF8' in source


def test_offline_acceptance_has_timestamped_json_and_log_evidence_metadata():
    source = (SCRIPTS / "offline_acceptance.ps1").read_text(encoding="utf-8")

    assert '"yyyyMMdd-HHmmss"' in source
    assert '"acceptance-$($script:RunStamp).log"' in source
    assert '"acceptance-$($script:RunStamp).json"' in source
    assert "commit_hash = $null" in source
    assert "ollama_host = $null" in source
    assert "ollama_version = $null" in source
    assert "model = $null" in source
    assert "seed = $null" in source
    assert "temperature = $null" in source
    assert '$script:Evidence["steps"]' in source
    assert '$script:Evidence["overall_result"]' in source
    assert 'Set-Content -LiteralPath $script:JsonPath -Encoding UTF8' in source
