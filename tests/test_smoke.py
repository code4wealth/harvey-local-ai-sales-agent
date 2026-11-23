"""Repository baseline checks that do not require Ollama or model downloads."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_python_version():
    assert sys.version_info >= (3, 11)


def test_verify_script_exists_and_mentions_local_only():
    script = ROOT / "scripts" / "verify_no_cloud.py"
    assert script.is_file()
    assert "127.0.0.1" in script.read_text()


def test_no_legacy_package():
    assert not (ROOT / "sellbird").exists()
    assert not (ROOT / "harvey").exists()


def test_ollama_smoke_schema_is_nested():
    from scripts.smoke_ollama import SmokeResponse

    schema = SmokeResponse.model_json_schema()
    assert "$defs" in schema
    assert "$ref" in schema["properties"]["details"]
