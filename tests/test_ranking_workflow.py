from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app import batch, db, llm_client, prospects
from app.main import app


def _get(path: str) -> httpx.Response:
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(request())


def _icp(*, industry: str, pain_point: str, trigger: str, disqualifier: str) -> dict:
    return {
        "industries": [industry],
        "company_size": {"min": 50, "max": 200},
        "buyer_titles": ["Sales Director"],
        "pain_points": [pain_point],
        "trigger_events": [trigger],
        "disqualifiers": [disqualifier],
    }


def _save_icp(conn, product_id: int, value: dict) -> None:
    conn.execute(
        "INSERT INTO icps "
        "(product_id, icp_json, embedding, embedding_model, model_name, created_at) "
        "VALUES (?, ?, NULL, '', 'mock-icp', ?)",
        (product_id, json.dumps(value, sort_keys=True), db.utcnow()),
    )
    conn.commit()


def _save_signal_run(conn, prospect_id: int, signals: list[dict], *, status: str) -> int:
    run_id = db.create_signal_run(conn, prospect_id=prospect_id, model_name="mock-signals")
    product_id = db.get_prospect(conn, prospect_id)["product_id"]
    conn.execute(
        "UPDATE signal_runs SET status = ?, signals_json = ?, drop_counts_json = '{}', "
        "removed_content_json = '{}' WHERE id = ?",
        (status, json.dumps(signals, sort_keys=True), run_id),
    )
    for signal in signals:
        conn.execute(
            "INSERT INTO signals "
            "(prospect_id, signal_run_id, type, evidence, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                prospect_id,
                run_id,
                signal["type"],
                signal["evidence"],
                signal["confidence"],
                db.utcnow(),
            ),
        )
    conn.commit()
    assert product_id is not None
    return run_id


def _use_mock_embeddings(monkeypatch) -> None:
    def embed_texts(texts, *, model_name):
        vectors = []
        for text in texts:
            value = json.loads(text)
            industry = (value.get("industries") or [""])[0]
            vectors.append([1.0, 0.0] if industry == "retail operations" else [0.0, 1.0])
        return vectors

    monkeypatch.setattr(batch, "embed_texts", embed_texts)
    monkeypatch.setattr(batch, "embed_long_text", lambda _text, *, model_name: [1.0, 0.0])


def test_ranking_is_product_scoped_and_uses_only_verified_signal_runs(
    db_path, monkeypatch, tmp_path
):
    page_dir = tmp_path / "pages"
    monkeypatch.setattr(prospects, "DEFAULT_PAGE_DIR", page_dir)
    _use_mock_embeddings(monkeypatch)
    monkeypatch.setattr(
        llm_client,
        "generate_json",
        lambda *args, **kwargs: pytest.fail("ranking must not call an LLM"),
    )
    conn = db.connect()
    try:
        retail_product = db.create_product(conn, name="Retail product")
        healthcare_product = db.create_product(conn, name="Healthcare product")
        page_text = "Our retail operations use manual handoffs. The team hired five people."
        retail_prospect = db.create_prospect(
            conn,
            product_id=retail_product,
            company_name="Shared company",
            company_domain="shared.example",
            contact_title="Sales Director",
            employee_count=100,
        )
        healthcare_prospect = db.create_prospect(
            conn,
            product_id=healthcare_product,
            company_name="Shared company",
            company_domain="shared.example",
            contact_title="Sales Director",
            employee_count=100,
        )
        prospects.store_prospect_page(
            conn, prospect_id=retail_prospect, text=page_text, page_dir=page_dir
        )
        prospects.store_prospect_page(
            conn, prospect_id=healthcare_prospect, text=page_text, page_dir=page_dir
        )
        _save_icp(
            conn,
            retail_product,
            _icp(
                industry="retail operations",
                pain_point="manual handoffs",
                trigger="hired five people",
                disqualifier="no retail operations",
            ),
        )
        _save_icp(
            conn,
            healthcare_product,
            _icp(
                industry="healthcare clinics",
                pain_point="manual triage",
                trigger="opening a clinic",
                disqualifier="organizations without a clinic",
            ),
        )
        _save_signal_run(
            conn,
            retail_prospect,
            [
                {
                    "type": "hiring",
                    "evidence": "The team hired five people.",
                    "confidence": 0.8,
                }
            ],
            status="succeeded",
        )
        # A failed run's row is deliberately not trusted or used in the score.
        failed_run = _save_signal_run(
            conn,
            retail_prospect,
            [
                {
                    "type": "funding",
                    "evidence": "An unverified funding claim.",
                    "confidence": 1.0,
                }
            ],
            status="failed",
        )
        _save_signal_run(conn, healthcare_prospect, [], status="succeeded")
    finally:
        conn.close()

    retail_report = _get(f"/api/products/{retail_product}/ranking").json()
    healthcare_report = _get(f"/api/products/{healthcare_product}/ranking").json()
    retail = retail_report["prospects"][0]
    healthcare = healthcare_report["prospects"][0]

    assert retail_report["product_id"] == retail_product
    assert healthcare_report["product_id"] == healthcare_product
    assert [row["prospect_id"] for row in retail_report["prospects"]] == [retail_prospect]
    assert [row["prospect_id"] for row in healthcare_report["prospects"]] == [healthcare_prospect]
    assert retail["company_name"] == healthcare["company_name"] == "Shared company"
    assert retail["score"] == pytest.approx(72.0)
    assert retail["tier"] == "high"
    assert retail["partial"] is False
    assert retail["signals_status"] == "available"
    assert retail["latest_signal_run_status"] == "failed"
    assert retail["signal_run_id"] != failed_run
    assert retail["score_breakdown"]["signal_score"] == pytest.approx(20.0)
    assert retail["verified_signal_reasons"] == [
        {
            "type": "hiring",
            "evidence": "The team hired five people.",
            "confidence": 0.8,
            "signal_run_id": retail["signal_run_id"],
        }
    ]
    assert retail["icp_field_matches"]["industries"]["status"] == "matched"
    assert retail["icp_field_matches"]["company_size"]["status"] == "matched"
    assert retail["icp_field_matches"]["buyer_titles"]["status"] == "matched"
    assert retail["icp_field_matches"]["pain_points"]["matches"] == ["manual handoffs"]

    assert healthcare["score"] == pytest.approx(30.0)
    assert healthcare["tier"] == "low"
    assert healthcare["partial"] is False
    assert healthcare["signals_status"] == "none_found"
    assert "signals" not in healthcare["missing_inputs"]
    assert healthcare["verified_signal_reasons"] == []
    assert healthcare["icp_field_matches"]["industries"]["status"] == "no_exact_match"
    assert retail["score"] > healthcare["score"]


def test_missing_icp_and_signals_never_produce_a_default_score(db_path, monkeypatch):
    monkeypatch.setattr(
        llm_client,
        "generate_json",
        lambda *args, **kwargs: pytest.fail("ranking must not call an LLM"),
    )
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="Unconfigured product")
        prospect_id = db.create_prospect(
            conn, product_id=product_id, company_name="Unranked company"
        )
        conn.commit()
    finally:
        conn.close()

    response = _get(f"/api/products/{product_id}/ranking")
    assert response.status_code == 200
    report = response.json()
    prospect = report["prospects"][0]
    assert report["icp_status"] == "missing"
    assert prospect["prospect_id"] == prospect_id
    assert prospect["score"] is None
    assert prospect["tier"] == "unranked"
    assert prospect["partial"] is True
    assert {"icp", "signals", "page_text"} <= set(prospect["missing_inputs"])
    assert prospect["signals_status"] == "missing"
    assert prospect["verified_signal_reasons"] == []
    assert prospect["score_breakdown"] is None
    assert all(
        field["status"] == "unknown"
        for field in prospect["icp_field_matches"].values()
    )
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 0
    finally:
        conn.close()
