from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.mark.parametrize("name", ["offline_acceptance.ps1", "ollama_down_check.ps1"])
def test_power_shell_acceptance_scripts_are_loopback_only_and_text_free(name):
    source = (SCRIPTS / name).read_text(encoding="utf-8")

    assert '"http://127.0.0.1:8000"' in source
    assert "$handler.UseProxy = $false" in source
    assert "$handler.AllowAutoRedirect = $false" in source
    assert '"test_evidence\\offline"' in source
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
