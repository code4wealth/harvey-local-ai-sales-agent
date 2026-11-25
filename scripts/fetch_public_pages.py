#!/usr/bin/env python3
"""Optional ONLINE research helper for URLs supplied in a CSV.

This script is not part of the offline AI workflow. It fetches public web pages
only when an operator explicitly runs it, checks robots.txt before each page,
extracts readable text with BeautifulSoup, and saves UTF-8 text files under
data/prospect_pages/. It never imports or calls the local LLM client.

CSV format: a header named ``url`` (case-insensitive), followed by one HTTP(S)
URL per row. The printed output gives the filename to put in a prospect CSV's
``page_text_path`` column. Review the site's terms and the collected text before
using it. Do not use this helper to access private, login-only, or paywalled
content.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import ipaddress
import re
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "data" / "prospect_pages"
USER_AGENT = "HarveyLocalSalesAgentResearch/0.1"
MAX_REDIRECTS = 5
MAX_PAGE_BYTES = 1_000_000
MAX_ROBOTS_BYTES = 256_000
CHUNK_BYTES = 64 * 1024
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class PublicFetchError(RuntimeError):
    """A URL could not be safely fetched or parsed."""


class RobotsDenied(PublicFetchError):
    """robots.txt disallows fetching the requested URL."""


def validate_public_url(value: str) -> str:
    """Validate and normalize a public HTTP(S) URL; reject local/private hosts."""
    if not isinstance(value, str) or not value.strip():
        raise PublicFetchError("URL is empty")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PublicFetchError("URL is malformed") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise PublicFetchError("only public HTTP and HTTPS URLs are allowed")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise PublicFetchError("URL must have a public hostname and no embedded credentials")
    if parsed.fragment:
        raise PublicFetchError("URL fragments are not needed; remove the fragment")
    if port is not None and port not in {80, 443}:
        raise PublicFetchError("only standard public web ports 80 and 443 are allowed")

    host = parsed.hostname.rstrip(".").casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
        raise PublicFetchError("local hostnames are not allowed")
    lookup_port = port or (443 if parsed.scheme.casefold() == "https" else 80)
    try:
        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            records = socket.getaddrinfo(host, lookup_port, type=socket.SOCK_STREAM)
            addresses = {
                ipaddress.ip_address(record[4][0].split("%", 1)[0])
                for record in records
            }
    except (OSError, ValueError) as exc:
        raise PublicFetchError(f"could not resolve public hostname {host!r}") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise PublicFetchError("URL must resolve only to globally routable public addresses")

    # Drop fragments and preserve the query; requests never sends fragments.
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc, parsed.path or "/", parsed.query, ""))


def read_url_csv(csv_path: str | Path) -> list[tuple[int, str]]:
    """Read a CSV with a case-insensitive ``url`` column."""
    try:
        with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise PublicFetchError("CSV must contain a header row with a 'url' column")
            url_header = next((name for name in reader.fieldnames if name.strip().casefold() == "url"), None)
            if url_header is None:
                raise PublicFetchError("CSV is missing the required 'url' column")
            rows = []
            for line_number, row in enumerate(reader, start=2):
                rows.append((line_number, str(row.get(url_header) or "").strip()))
            return rows
    except OSError as exc:
        raise PublicFetchError(f"could not read CSV file: {exc}") from exc


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _bounded_body(response: requests.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
        if not chunk:
            continue
        size += len(chunk)
        if size > limit:
            raise PublicFetchError(f"response exceeds the {limit:,}-byte size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _polite_get(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    minimum_delay: float,
    last_request_at: dict[str, float],
    sleep,
) -> requests.Response:
    origin = _origin(url)
    wait = minimum_delay - (time.monotonic() - last_request_at.get(origin, 0.0))
    if wait > 0:
        sleep(wait)
    try:
        response = session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as exc:
        raise PublicFetchError(f"request failed for {origin}: {type(exc).__name__}") from exc
    last_request_at[origin] = time.monotonic()
    return response


def _robots_parser(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    delay: float,
    last_request_at: dict[str, float],
    cache: dict[str, RobotFileParser],
    sleep,
) -> RobotFileParser:
    origin = _origin(url)
    if origin in cache:
        return cache[origin]

    robots_url = f"{origin}/robots.txt"
    parser = RobotFileParser(robots_url)
    response = _polite_get(
        session,
        robots_url,
        timeout=timeout,
        minimum_delay=delay,
        last_request_at=last_request_at,
        sleep=sleep,
    )
    try:
        status = int(response.status_code)
        if 200 <= status < 300:
            body = _bounded_body(response, MAX_ROBOTS_BYTES)
            encoding = getattr(response, "encoding", None) or "utf-8"
            parser.parse(body.decode(encoding, errors="replace").splitlines())
        elif status in {404, 410}:
            # A missing robots.txt means there are no published crawl rules.
            parser.parse([])
        else:
            # Fail closed on redirects, access errors, rate limits, and server errors.
            parser.parse(["User-agent: *", "Disallow: /"])
    finally:
        response.close()
        session.cookies.clear()
    cache[origin] = parser
    return parser


def _extract_text(content: bytes, content_type: str, encoding: str | None = None) -> str:
    media_type = content_type.split(";", 1)[0].strip().casefold()
    if media_type == "text/html" or media_type in {"application/xhtml+xml"}:
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "nav", "footer", "form"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        main = soup.body or soup
        text = "\n".join(part.strip() for part in main.stripped_strings if part.strip())
        if title and title.casefold() not in text.casefold():
            text = f"{title}\n\n{text}" if text else title
        return text.strip()
    if media_type == "text/plain":
        return content.decode(encoding or "utf-8", errors="replace").strip()
    raise PublicFetchError(f"unsupported content type {media_type or '(missing)'}; HTML or plain text is required")


def _fetch_page_text(
    url: str,
    session: requests.Session,
    *,
    timeout: float,
    delay: float,
    max_bytes: int,
    robots_cache: dict[str, RobotFileParser],
    last_request_at: dict[str, float],
    sleep,
) -> tuple[str, str]:
    current_url = validate_public_url(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        current_url = validate_public_url(current_url)
        robots = _robots_parser(
            session,
            current_url,
            timeout=timeout,
            delay=delay,
            last_request_at=last_request_at,
            cache=robots_cache,
            sleep=sleep,
        )
        if not robots.can_fetch(USER_AGENT, current_url):
            raise RobotsDenied(f"robots.txt disallows {current_url}")
        crawl_delay = robots.crawl_delay(USER_AGENT) or 0.0
        response = _polite_get(
            session,
            current_url,
            timeout=timeout,
            minimum_delay=max(delay, float(crawl_delay)),
            last_request_at=last_request_at,
            sleep=sleep,
        )
        try:
            status = int(response.status_code)
            if status in _REDIRECT_CODES:
                location = response.headers.get("Location")
                if not location:
                    raise PublicFetchError("server returned a redirect without a Location header")
                if redirect_count >= MAX_REDIRECTS:
                    raise PublicFetchError(f"page exceeded {MAX_REDIRECTS} redirects")
                current_url = validate_public_url(urljoin(current_url, location))
                continue
            if status < 200 or status >= 300:
                raise PublicFetchError(f"page returned HTTP {status}")
            content_type = response.headers.get("Content-Type", "")
            body = _bounded_body(response, max_bytes)
            text = _extract_text(body, content_type, getattr(response, "encoding", None))
            if not text:
                raise PublicFetchError("page contained no readable text")
            return current_url, text
        finally:
            response.close()
            session.cookies.clear()
    raise PublicFetchError("page redirect handling ended unexpectedly")


def _output_filename(url: str) -> str:
    parsed = urlsplit(url)
    tail = Path(parsed.path).stem or "page"
    slug = re.sub(r"[^a-z0-9]+", "_", f"{parsed.hostname}_{tail}".casefold()).strip("_")[:48]
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"public_{slug or 'page'}_{digest}.txt"


def fetch_csv_pages(
    csv_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    timeout: float = 20.0,
    delay: float = 1.0,
    max_bytes: int = MAX_PAGE_BYTES,
    session: requests.Session | None = None,
    sleep=time.sleep,
) -> list[dict[str, str | int]]:
    """Fetch URLs in a CSV, returning saved/skipped/failed row summaries.

    ``session`` and ``sleep`` are injectable for tests; the command-line entry
    point uses a requests session with environment proxies disabled.
    """
    if timeout <= 0 or delay < 0 or max_bytes <= 0:
        raise ValueError("timeout and max_bytes must be positive; delay must be non-negative")
    rows = read_url_csv(csv_path)
    owned_session = session is None
    http = session or requests.Session()
    if owned_session:
        http.trust_env = False
        http.headers.update({"User-Agent": USER_AGENT})

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    robots_cache: dict[str, RobotFileParser] = {}
    last_request_at: dict[str, float] = {}
    results: list[dict[str, str | int]] = []
    try:
        for line_number, raw_url in rows:
            if not raw_url:
                results.append({"row": line_number, "status": "failed", "detail": "URL is empty"})
                continue
            try:
                safe_url = validate_public_url(raw_url)
                final_url, text = _fetch_page_text(
                    safe_url,
                    http,
                    timeout=timeout,
                    delay=delay,
                    max_bytes=max_bytes,
                    robots_cache=robots_cache,
                    last_request_at=last_request_at,
                    sleep=sleep,
                )
                path = destination / _output_filename(final_url)
                path.write_text(text + "\n", encoding="utf-8")
                try:
                    page_text_path = path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
                except ValueError:
                    page_text_path = path.as_posix()
                results.append({
                    "row": line_number,
                    "status": "saved",
                    "url": final_url,
                    "page_text_path": page_text_path,
                })
            except RobotsDenied as exc:
                results.append({"row": line_number, "status": "skipped_robots", "detail": str(exc)})
            except (PublicFetchError, OSError) as exc:
                results.append({"row": line_number, "status": "failed", "detail": str(exc)})
    finally:
        if owned_session:
            http.close()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV containing one URL per row in a 'url' column")
    parser.add_argument("--timeout", type=float, default=20.0, help="request timeout in seconds (default: 20)")
    parser.add_argument("--delay", type=float, default=1.0, help="minimum per-host delay in seconds (default: 1)")
    parser.add_argument("--max-bytes", type=int, default=MAX_PAGE_BYTES, help="maximum bytes per page (default: 1000000)")
    args = parser.parse_args(argv)

    print("ONLINE RESEARCH: fetching only user-supplied public URLs; this is not part of the offline AI workflow.")
    try:
        results = fetch_csv_pages(
            args.csv_file,
            timeout=args.timeout,
            delay=args.delay,
            max_bytes=args.max_bytes,
        )
    except (PublicFetchError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for result in results:
        status = str(result["status"]).upper()
        location = result.get("page_text_path") or result.get("detail") or ""
        print(f"[{status}] CSV row {result['row']}: {location}")
    return 1 if any(result["status"] == "failed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
