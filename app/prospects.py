"""Deterministic product/prospect import and local page-text storage."""

from __future__ import annotations

import csv
import io
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
from typing import Any

from app import db

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE_DIR = REPO_ROOT / "data" / "prospect_pages"
CSV_FIELDS = (
    "contact_name",
    "contact_title",
    "company_name",
    "company_domain",
    "employee_count",
    "contact_email",
    "page_text_path",
    "do_not_contact",
)
_REQUIRED_CSV_FIELDS = {"company_name"}
_HEADER_SEPARATORS = re.compile(r"[\s-]+")


class ProductNotFound(LookupError):
    """The requested product does not exist."""


class ProspectNotFound(LookupError):
    """The requested prospect does not exist."""


class ProspectImportError(ValueError):
    """A CSV row or header does not match the import contract."""


class ProspectPageError(ValueError):
    """A local page path is invalid or escapes the permitted page directory."""


def _normalize_header(value: str) -> str:
    return _HEADER_SEPARATORS.sub("_", value.lstrip("\ufeff").strip().lower())


def _parse_employee_count(value: str, row_number: int) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        count = int(value)
    except ValueError as exc:
        raise ProspectImportError(
            f"row {row_number}: employee_count must be a whole number"
        ) from exc
    if count < 0:
        raise ProspectImportError(f"row {row_number}: employee_count must be non-negative")
    return count


def _parse_do_not_contact(value: str, row_number: int) -> bool:
    value = value.strip().casefold()
    if value in {"", "0", "false", "no", "n"}:
        return False
    if value in {"1", "true", "yes", "y"}:
        return True
    raise ProspectImportError(
        f"row {row_number}: do_not_contact must be true/false, yes/no, or 1/0"
    )


def _parse_csv(csv_text: str) -> list[dict[str, Any]]:
    if not isinstance(csv_text, str):
        raise TypeError("CSV content must be a string")
    try:
        reader = csv.reader(io.StringIO(csv_text, newline=""))
        raw_headers = next(reader, None)
    except csv.Error as exc:
        raise ProspectImportError(f"invalid CSV header: {exc}") from exc
    if not raw_headers:
        raise ProspectImportError("CSV must include a header row")
    headers = [_normalize_header(header) for header in raw_headers]
    if any(not header for header in headers):
        raise ProspectImportError("CSV headers must not be empty")
    if len(set(headers)) != len(headers):
        raise ProspectImportError("CSV contains duplicate headers after normalization")
    missing = _REQUIRED_CSV_FIELDS - set(headers)
    if missing:
        raise ProspectImportError(
            "CSV is missing required header(s): " + ", ".join(sorted(missing))
        )

    records: list[dict[str, Any]] = []
    try:
        for row_number, values in enumerate(reader, start=2):
            if not any(value.strip() for value in values):
                continue
            if len(values) > len(headers):
                raise ProspectImportError(f"row {row_number}: contains more values than headers")
            values += [""] * (len(headers) - len(values))
            raw = {header: value.strip() for header, value in zip(headers, values)}
            company_name = raw.get("company_name", "").strip()
            if not company_name:
                raise ProspectImportError(f"row {row_number}: company_name must not be empty")
            employee_count = _parse_employee_count(raw.get("employee_count", ""), row_number)
            do_not_contact = _parse_do_not_contact(
                raw.get("do_not_contact", ""), row_number
            )
            page_text_path = raw.get("page_text_path", "").strip()
            if page_text_path and "://" in page_text_path:
                raise ProspectImportError(
                    f"row {row_number}: page_text_path must be local; URLs are not fetched"
                )
            if page_text_path:
                try:
                    resolve_page_path(page_text_path)
                except ProspectPageError as exc:
                    raise ProspectImportError(
                        f"row {row_number}: page_text_path must remain inside data/prospect_pages"
                    ) from exc
            records.append(
                {
                    "contact_name": raw.get("contact_name", ""),
                    "contact_title": raw.get("contact_title", ""),
                    "company_name": company_name,
                    "company_domain": raw.get("company_domain", ""),
                    "employee_count": employee_count,
                    "contact_email": raw.get("contact_email", ""),
                    "page_text_path": page_text_path,
                    "do_not_contact": do_not_contact,
                }
            )
    except csv.Error as exc:
        raise ProspectImportError(f"invalid CSV data: {exc}") from exc
    return records


def _prospect_dedupe_key(
    product_id: int, company_name: str, company_domain: str
) -> tuple[int, str]:
    identity = company_domain.strip().casefold() or company_name.strip().casefold()
    return int(product_id), identity


def import_prospects_csv(
    conn: sqlite3.Connection, *, product_id: int, csv_text: str
) -> tuple[int, int]:
    """Import rows atomically; return (inserted_count, skipped_duplicate_count)."""
    if db.get_product(conn, product_id) is None:
        raise ProductNotFound(f"product {product_id} not found")
    records = _parse_csv(csv_text)

    # Serialize the existence check and inserts so concurrent imports cannot
    # both pass the dedupe check for the same product/company key.
    conn.execute("BEGIN IMMEDIATE")
    try:
        if db.get_product(conn, product_id) is None:
            raise ProductNotFound(f"product {product_id} not found")
        existing = conn.execute(
            "SELECT company_name, company_domain FROM prospects WHERE product_id = ?",
            (int(product_id),),
        ).fetchall()
        seen = {
            _prospect_dedupe_key(
                int(product_id), row["company_name"], row["company_domain"]
            )
            for row in existing
        }
        imported = 0
        skipped = 0
        for record in records:
            key = _prospect_dedupe_key(
                int(product_id), record["company_name"], record["company_domain"]
            )
            if key in seen:
                skipped += 1
                continue
            db.create_prospect(conn, product_id=product_id, **record)
            seen.add(key)
            imported += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return imported, skipped


def import_prospects_csv_file(
    conn: sqlite3.Connection, *, product_id: int, csv_path: str | Path
) -> tuple[int, int]:
    """Read a local CSV as UTF-8-with-BOM support, then import atomically."""
    try:
        with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as csv_file:
            csv_text = csv_file.read()
    except UnicodeDecodeError as exc:
        raise ProspectImportError("CSV file must be UTF-8 encoded") from exc
    except OSError as exc:
        raise ProspectImportError(f"cannot read CSV file: {exc}") from exc
    return import_prospects_csv(conn, product_id=product_id, csv_text=csv_text)


def resolve_page_path(
    page_text_path: str, *, page_dir: str | Path | None = None
) -> Path:
    """Resolve a relative page path strictly inside the local page directory."""
    if not isinstance(page_text_path, str) or not page_text_path.strip():
        raise ProspectPageError("page_text_path must be a non-empty relative path")
    normalized_separators = page_text_path.replace("\\", "/")
    posix_path = PurePosixPath(normalized_separators)
    windows_path = PureWindowsPath(page_text_path)
    if (
        Path(page_text_path).is_absolute()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in posix_path.parts
    ):
        raise ProspectPageError("page_text_path must be relative and contain no '..' components")

    root = Path(DEFAULT_PAGE_DIR if page_dir is None else page_dir).resolve()
    raw_path = Path(normalized_separators)
    repo_relative = (REPO_ROOT / raw_path).resolve()
    candidate = (
        repo_relative
        if repo_relative.is_relative_to(root)
        else (root / raw_path).resolve()
    )
    if candidate == root or not candidate.is_relative_to(root):
        raise ProspectPageError("page_text_path must remain inside data/prospect_pages")
    return candidate


def store_prospect_page(
    conn: sqlite3.Connection,
    *,
    prospect_id: int,
    text: str,
    page_dir: str | Path | None = None,
) -> str:
    """Persist UTF-8 page text locally and attach its relative filename to a prospect."""
    if not isinstance(text, str):
        raise TypeError("page text must be a string")
    if db.get_prospect(conn, prospect_id) is None:
        raise ProspectNotFound(f"prospect {prospect_id} not found")
    root = Path(DEFAULT_PAGE_DIR if page_dir is None else page_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = resolve_page_path(f"{int(prospect_id)}.txt", page_dir=root)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="")
        temporary.replace(path)
        db.update_prospect_page_path(conn, prospect_id, path.name)
        conn.commit()
    except Exception:
        conn.rollback()
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path.name


def load_prospect_page(
    conn: sqlite3.Connection,
    prospect_id: int,
    *,
    page_dir: str | Path | None = None,
) -> str:
    """Read a prospect's explicitly stored local page file; never fetch a URL."""
    prospect = db.get_prospect(conn, prospect_id)
    if prospect is None:
        raise ProspectNotFound(f"prospect {prospect_id} not found")
    page_text_path = prospect["page_text_path"]
    if not page_text_path:
        raise FileNotFoundError(f"prospect {prospect_id} has no local page text")
    path = resolve_page_path(page_text_path, page_dir=page_dir)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"local page text is unavailable for prospect {prospect_id}") from exc
    except UnicodeDecodeError as exc:
        raise ProspectPageError(f"page text for prospect {prospect_id} is not UTF-8") from exc
