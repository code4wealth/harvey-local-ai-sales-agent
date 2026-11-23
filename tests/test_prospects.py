from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import db, embeddings, prospects


def _create_product(conn):
    product_id = db.create_product(conn, name="Local CRM", description="Test product")
    conn.commit()
    return product_id


def test_import_prospects_csv_normalizes_headers_and_persists_fields(db_path, tmp_path, monkeypatch):
    page_dir = tmp_path / "prospect_pages"
    monkeypatch.setattr(prospects, "DEFAULT_PAGE_DIR", page_dir)
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        page_dir.mkdir()
        (page_dir / "acme.txt").write_text("Acme local page text", encoding="utf-8")
        csv_text = (
            "Contact Name,Contact Title,Company Name,Company Domain,Employee Count,"
            "Contact Email,Page Text Path,Do Not Contact\n"
            "Ada Example,VP of Operations,Acme,acme.test,120,ada@acme.test,acme.txt,yes\n"
        )
        imported, skipped = prospects.import_prospects_csv(
            conn, product_id=product_id, csv_text=csv_text
        )
        assert imported == 1
        assert skipped == 0
        row = db.list_prospects(conn, product_id)[0]
        assert row["contact_name"] == "Ada Example"
        assert row["contact_title"] == "VP of Operations"
        assert row["company_name"] == "Acme"
        assert row["employee_count"] == 120
        assert row["contact_email"] == "ada@acme.test"
        assert row["page_text_path"] == "acme.txt"
        assert row["do_not_contact"] == 1
        assert prospects.load_prospect_page(conn, row["id"]) == "Acme local page text"
    finally:
        conn.close()


def test_csv_file_import_reads_excel_bom_as_utf8_sig(db_path, tmp_path):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        csv_path = tmp_path / "excel-export.csv"
        csv_path.write_bytes(
            "\ufeffcompany_name,employee_count\r\nAcme,25\r\n".encode("utf-8")
        )
        assert prospects.import_prospects_csv_file(
            conn, product_id=product_id, csv_path=csv_path
        ) == (1, 0)
        assert db.list_prospects(conn, product_id)[0]["company_name"] == "Acme"
    finally:
        conn.close()


def test_csv_file_import_reports_row_error_without_partial_import(db_path, tmp_path):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        csv_path = tmp_path / "bad-row.csv"
        csv_path.write_bytes(
            "\ufeffcompany_name,employee_count\r\nGood Co,25\r\nBad Co,2.5\r\n".encode(
                "utf-8"
            )
        )
        with pytest.raises(prospects.ProspectImportError, match="row 3: employee_count"):
            prospects.import_prospects_csv_file(
                conn, product_id=product_id, csv_path=csv_path
            )
        assert db.list_prospects(conn, product_id) == []
    finally:
        conn.close()


def test_csv_import_skips_existing_and_in_file_duplicates(db_path):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        csv_text = (
            "company_name,company_domain\n"
            "Acme Inc,acme.example\n"
            "Acme Group,ACME.EXAMPLE\n"
            "Solo Company,\n"
            "solo company,\n"
        )
        assert prospects.import_prospects_csv(
            conn, product_id=product_id, csv_text=csv_text
        ) == (2, 2)
        assert len(db.list_prospects(conn, product_id)) == 2
        assert prospects.import_prospects_csv(
            conn, product_id=product_id, csv_text=csv_text
        ) == (0, 4)
        assert len(db.list_prospects(conn, product_id)) == 2

        another_product = db.create_product(conn, name="Other product")
        conn.commit()
        assert prospects.import_prospects_csv(
            conn,
            product_id=another_product,
            csv_text="company_name,company_domain\nAcme,acme.example\n",
        ) == (1, 0)
    finally:
        conn.close()


def test_csv_import_rolls_back_partial_insert_on_database_error(db_path, monkeypatch):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        original_create = db.create_prospect
        calls = 0

        def fail_on_second_insert(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise sqlite3.IntegrityError("simulated insert failure")
            return original_create(*args, **kwargs)

        monkeypatch.setattr(db, "create_prospect", fail_on_second_insert)
        with pytest.raises(sqlite3.IntegrityError, match="simulated insert failure"):
            prospects.import_prospects_csv(
                conn,
                product_id=product_id,
                csv_text="company_name\nFirst Co\nSecond Co\n",
            )
        assert db.list_prospects(conn, product_id) == []
    finally:
        conn.close()


def test_csv_import_is_atomic_and_rejects_invalid_rows(db_path):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        with pytest.raises(prospects.ProspectImportError, match="whole number"):
            prospects.import_prospects_csv(
                conn,
                product_id=product_id,
                csv_text="company_name,employee_count\nGood Co,20\nBad Co,1.5\n",
            )
        assert db.list_prospects(conn, product_id) == []
    finally:
        conn.close()


def test_csv_import_requires_product_and_blocks_path_escape(db_path, tmp_path):
    conn = db.connect()
    try:
        with pytest.raises(prospects.ProductNotFound):
            prospects.import_prospects_csv(
                conn, product_id=999, csv_text="company_name\nAcme\n"
            )
        product_id = _create_product(conn)
        with pytest.raises(prospects.ProspectImportError, match="page_text_path"):
            prospects.import_prospects_csv(
                conn,
                product_id=product_id,
                csv_text="company_name,page_text_path\nAcme,../../outside.txt\n",
            )
        with pytest.raises(prospects.ProspectImportError, match="URLs are not fetched"):
            prospects.import_prospects_csv(
                conn,
                product_id=product_id,
                csv_text="company_name,page_text_path\nAcme,https://example.test\n",
            )
        assert db.list_prospects(conn, product_id) == []
    finally:
        conn.close()


@pytest.mark.parametrize(
    "bad_path",
    [
        "../secrets.txt",
        r"..\..\secrets.txt",
        "/etc/passwd",
        r"C:\Windows\win.ini",
    ],
)
def test_resolve_page_path_rejects_traversal_and_absolute_paths_cross_platform(
    tmp_path, bad_path
):
    with pytest.raises(prospects.ProspectPageError):
        prospects.resolve_page_path(bad_path, page_dir=tmp_path / "prospect_pages")
    absolute_inside = tmp_path / "prospect_pages" / "safe.txt"
    with pytest.raises(prospects.ProspectPageError):
        prospects.resolve_page_path(str(absolute_inside), page_dir=tmp_path / "prospect_pages")


def test_default_page_dir_is_repo_anchored_from_a_different_cwd(tmp_path, monkeypatch):
    repo_root = Path(prospects.__file__).resolve().parents[1]
    expected_root = repo_root / "data" / "prospect_pages"
    monkeypatch.chdir(tmp_path)

    assert prospects.DEFAULT_PAGE_DIR == expected_root
    assert prospects.resolve_page_path("nested/company.txt") == (
        expected_root / "nested" / "company.txt"
    )


def test_store_and_load_prospect_page_uses_local_utf8_file(db_path, tmp_path):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        prospect_id = db.create_prospect(
            conn, product_id=product_id, company_name="Acme", page_text_path=""
        )
        conn.execute(
            "UPDATE prospects SET page_embedding = ?, page_embedding_model = ? WHERE id = ?",
            (embeddings.pack_embedding([1.0, 0.0]), embeddings.DEFAULT_MODEL, prospect_id),
        )
        conn.commit()
        page_dir = tmp_path / "pages"
        content = "Public page excerpt — café operations"
        assert prospects.store_prospect_page(
            conn, prospect_id=prospect_id, text=content, page_dir=page_dir
        ) == f"{prospect_id}.txt"
        assert prospects.load_prospect_page(
            conn, prospect_id, page_dir=page_dir
        ) == content
        saved_prospect = db.get_prospect(conn, prospect_id)
        assert saved_prospect["page_text_path"] == f"{prospect_id}.txt"
        assert saved_prospect["page_embedding"] is None
        assert saved_prospect["page_embedding_model"] == ""
    finally:
        conn.close()


def test_load_prospect_page_reports_missing_file_and_blocks_escape(db_path, tmp_path):
    conn = db.connect()
    try:
        product_id = _create_product(conn)
        prospect_id = db.create_prospect(
            conn, product_id=product_id, company_name="Acme", page_text_path="missing.txt"
        )
        conn.commit()
        with pytest.raises(FileNotFoundError):
            prospects.load_prospect_page(conn, prospect_id, page_dir=tmp_path)
        db.update_prospect_page_path(conn, prospect_id, "../private.txt")
        conn.commit()
        with pytest.raises(prospects.ProspectPageError):
            prospects.load_prospect_page(conn, prospect_id, page_dir=tmp_path)
    finally:
        conn.close()
