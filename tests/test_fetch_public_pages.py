from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts import fetch_public_pages


PUBLIC_URL = "http://93.184.216.34/story"
ROBOTS_URL = "http://93.184.216.34/robots.txt"


class StubCookies:
    def clear(self):
        pass


class StubResponse:
    def __init__(self, status_code: int, body: bytes = b"", headers=None, url=""):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.url = url
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]

    def close(self):
        self.closed = True


class StubSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.cookies = StubCookies()

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        try:
            return self.responses[url]
        except KeyError as exc:
            raise AssertionError(f"unexpected HTTP request: {url}") from exc


def test_fetch_script_has_no_import_of_local_llm_client():
    source_path = Path(fetch_public_pages.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    assert "app.llm_client" not in imports
    assert not any(name.startswith("app.llm_client.") for name in imports)


def test_fetch_skips_a_url_disallowed_by_robots_txt():
    session = StubSession({
        ROBOTS_URL: StubResponse(
            200,
            b"User-agent: *\nDisallow: /private\n",
            {"Content-Type": "text/plain"},
            ROBOTS_URL,
        ),
    })
    last_request_at = {}
    robots_cache = {}

    with pytest.raises(fetch_public_pages.RobotsDenied, match="robots.txt disallows"):
        fetch_public_pages._fetch_page_text(
            "http://93.184.216.34/private",
            session,
            timeout=1,
            delay=0,
            max_bytes=1000,
            robots_cache=robots_cache,
            last_request_at=last_request_at,
            sleep=lambda _: None,
        )

    assert [call[0] for call in session.calls] == [ROBOTS_URL]
    assert session.calls[0][1]["allow_redirects"] is False


def test_csv_fetch_saves_clean_html_text_under_output_directory(tmp_path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text(f"URL\n{PUBLIC_URL}\n", encoding="utf-8")
    output_dir = tmp_path / "prospect_pages"
    html = (
        b"<html><head><title>Customer story</title><script>not evidence</script></head>"
        b"<body><nav>menu text</nav><main><p>Public case study content.</p></main></body></html>"
    )
    session = StubSession({
        ROBOTS_URL: StubResponse(200, b"User-agent: *\nAllow: /\n", {"Content-Type": "text/plain"}, ROBOTS_URL),
        PUBLIC_URL: StubResponse(200, html, {"Content-Type": "text/html; charset=utf-8"}, PUBLIC_URL),
    })

    results = fetch_public_pages.fetch_csv_pages(
        csv_path,
        output_dir,
        session=session,
        timeout=1,
        delay=0,
        sleep=lambda _: None,
    )

    assert results[0]["status"] == "saved"
    assert results[0]["page_text_path"] == (output_dir / fetch_public_pages._output_filename(PUBLIC_URL)).as_posix()
    saved_text = (output_dir / fetch_public_pages._output_filename(PUBLIC_URL)).read_text(encoding="utf-8")
    assert "Customer story" in saved_text
    assert "Public case study content." in saved_text
    assert "not evidence" not in saved_text
    assert "menu text" not in saved_text
    assert [call[0] for call in session.calls] == [ROBOTS_URL, PUBLIC_URL]
    for _, kwargs in session.calls:
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        assert kwargs["headers"]["User-Agent"] == fetch_public_pages.USER_AGENT


def test_fetch_rejects_private_hosts_and_redirects_to_local_addresses():
    with pytest.raises(fetch_public_pages.PublicFetchError, match="globally routable"):
        fetch_public_pages.validate_public_url("http://127.0.0.1/private")

    session = StubSession({
        ROBOTS_URL: StubResponse(200, b"User-agent: *\nAllow: /\n", {"Content-Type": "text/plain"}, ROBOTS_URL),
        PUBLIC_URL: StubResponse(302, b"", {"Location": "http://127.0.0.1/admin"}, PUBLIC_URL),
    })
    with pytest.raises(fetch_public_pages.PublicFetchError, match="globally routable"):
        fetch_public_pages._fetch_page_text(
            PUBLIC_URL,
            session,
            timeout=1,
            delay=0,
            max_bytes=1000,
            robots_cache={},
            last_request_at={},
            sleep=lambda _: None,
        )
    assert [call[0] for call in session.calls] == [ROBOTS_URL, PUBLIC_URL]
