from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlsplit

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
CLOUD_SDK_ROOTS = {
    "openai",
    "anthropic",
    "google",
    "cohere",
    "replicate",
    "groq",
    "mistralai",
    "together",
    "litellm",
    "vertexai",
    "boto3",
    "azure",
}
HTTP_CLIENT_ROOTS = {"httpx", "requests", "urllib", "urllib3", "aiohttp"}
NONLOCAL_CLIENT_IMPORTS = {
    "requests", "urllib", "urllib3", "aiohttp", "socket", "smtplib", "ftplib",
    "websocket", "websockets", "huggingface_hub",
}
# Pure URL parsing is not a transport; the urllib.request stack remains banned.
URL_PATTERN = re.compile(r"https?://[^\s\"'`]+", re.IGNORECASE)


def _qualified_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_local_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS
    except ValueError:
        return False


def _source_files() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def test_ai_path_has_no_cloud_sdk_imports_or_nonlocal_urls():
    offenders: list[str] = []
    sources = {path: path.read_text(encoding="utf-8") for path in _source_files()}
    ollama_url = None

    for path, source in sources.items():
        tree = ast.parse(source, filename=str(path))
        relative = path.relative_to(APP_ROOT.parent).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".", 1)[0] for alias in node.names]
                if any(name in CLOUD_SDK_ROOTS for name in imported):
                    offenders.append(f"{relative}:{node.lineno}: cloud SDK import")
                if any(name in NONLOCAL_CLIENT_IMPORTS for name in imported):
                    offenders.append(f"{relative}:{node.lineno}: external HTTP client import")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".", 1)[0]
                if root in CLOUD_SDK_ROOTS:
                    offenders.append(f"{relative}:{node.lineno}: cloud SDK import")
                if root in NONLOCAL_CLIENT_IMPORTS and node.module != "urllib.parse":
                    offenders.append(f"{relative}:{node.lineno}: external HTTP client import")

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "OLLAMA_URL":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            ollama_url = node.value.value

        for url in URL_PATTERN.findall(source):
            if not _is_local_url(url.rstrip(").,;")):
                offenders.append(f"{relative}: non-local URL")

    assert ollama_url is not None and _is_local_url(ollama_url), (
        "the fixed Ollama base URL must be loopback-only"
    )

    for path, source in sources.items():
        tree = ast.parse(source, filename=str(path))
        relative = path.relative_to(APP_ROOT.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            qualified = _qualified_name(node.func)
            root = qualified.split(".", 1)[0]
            if root not in HTTP_CLIENT_ROOTS:
                continue
            if qualified in {"httpx.Client", "httpx.AsyncClient"}:
                keywords = {item.arg: item.value for item in node.keywords if item.arg}
                base = keywords.get("base_url")
                if isinstance(base, ast.Constant) and isinstance(base.value, str):
                    if not _is_local_url(base.value):
                        offenders.append(f"{relative}:{node.lineno}: non-local HTTP base URL")
                elif isinstance(base, ast.Name) and base.id == "OLLAMA_URL":
                    if not _is_local_url(ollama_url or ""):
                        offenders.append(f"{relative}:{node.lineno}: non-local Ollama URL")
                else:
                    offenders.append(f"{relative}:{node.lineno}: HTTP client without fixed local base")
            elif qualified in {
                "httpx.get", "httpx.post", "httpx.put", "httpx.delete", "httpx.request",
                "requests.get", "requests.post", "requests.put", "requests.delete",
                "requests.request",
            }:
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    if not _is_local_url(first.value):
                        offenders.append(f"{relative}:{node.lineno}: non-local HTTP request")
                else:
                    offenders.append(f"{relative}:{node.lineno}: HTTP request without fixed local URL")

    assert not offenders, "AI network boundary violations:\n" + "\n".join(offenders)
