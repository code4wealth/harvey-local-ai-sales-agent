from __future__ import annotations

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
        imported = prospects.import_prospects_csv(
            conn, product_id=product_id, csv_text=csv_text
        )
        assert imported == 1
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
