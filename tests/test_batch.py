from __future__ import annotations

import json

import pytest

from app import batch, db, embeddings, prospects
from app.queue_worker import QueueWorker
import app.queue_worker as queue_worker
from app.embeddings import EmbeddingModelUnavailable
from app.llm_client import OllamaTimeout


def _product_and_prospect(conn):
    product_id = db.create_product(conn, name="Batch product")
    prospect_id = db.create_prospect(
        conn,
        product_id=product_id,
        contact_title="VP Sales",
        company_name="Acme",
        employee_count=100,
    )
    conn.commit()
    return product_id, prospect_id


def test_deterministic_csv_handler_runs_without_ollama(db_path, monkeypatch):
    batch.register_batch_handlers()
    monkeypatch.setattr(
        queue_worker, "ollama_up", lambda: pytest.fail("deterministic task must not probe Ollama")
    )
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="CSV product")
        conn.commit()
        task_id = db.enqueue_task(
            conn,
            batch.IMPORT_PROSPECTS_TASK,
            {
                "product_id": product_id,
                "csv_text": "company_name,employee_count\nAcme,12\n",
            },
        )
    finally:
        conn.close()

    assert QueueWorker().run_once() == 1
    conn = db.connect()
    try:
        assert db.get_task(conn, task_id)["status"] == "done"
        rows = db.list_prospects(conn, product_id)
        assert len(rows) == 1
        assert rows[0]["company_name"] == "Acme"
        assert rows[0]["employee_count"] == 12
    finally:
        conn.close()


def test_local_task_is_not_starved_by_older_llm_tasks_when_probe_times_out(db_path, monkeypatch):
    batch.register_batch_handlers()

    def slow_health_probe():
        raise OllamaTimeout("/api/tags timed out")

    monkeypatch.setattr(queue_worker, "ollama_up", slow_health_probe)
    queue_worker.register_handler("pending.llm.workflow", lambda payload: None)
    conn = db.connect()
    try:
        product_id = db.create_product(conn, name="CSV product")
        conn.commit()
        for _ in range(5):
            db.enqueue_task(conn, "pending.llm.workflow", {})
        local_id = db.enqueue_task(
            conn,
            batch.IMPORT_PROSPECTS_TASK,
            {"product_id": product_id, "csv_text": "company_name\nAcme\n"},
        )
    finally:
        conn.close()

    try:
        assert QueueWorker(batch_size=6).run_once() == 1
        conn = db.connect()
        try:
            assert db.get_task(conn, local_id)["status"] == "done"
            assert db.queue_counts(conn)["queued"] == 5
            assert len(db.list_prospects(conn, product_id)) == 1
        finally:
            conn.close()
    finally:
        queue_worker.HANDLERS.pop("pending.llm.workflow", None)


def test_deterministic_score_handler_uses_only_persisted_inputs(db_path, monkeypatch):
    batch.register_batch_handlers()
    monkeypatch.setattr(
        queue_worker, "ollama_up", lambda: pytest.fail("deterministic task must not probe Ollama")
    )
    conn = db.connect()
    try:
        product_id, prospect_id = _product_and_prospect(conn)
        now = db.utcnow()
        vector = embeddings.pack_embedding([1.0, 0.0])
        conn.execute(
            "INSERT INTO icps (product_id, icp_json, embedding, embedding_model, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                product_id,
                json.dumps({"company_size_min": 50, "company_size_max": 500, "buyer_titles": ["VP of Sales"]}),
                vector,
                embeddings.DEFAULT_MODEL,
                now,
            ),
        )
        conn.execute(
            "UPDATE prospects SET page_embedding = ?, page_embedding_model = ? WHERE id = ?",
            (vector, embeddings.DEFAULT_MODEL, prospect_id),
        )
        conn.execute(
            "INSERT INTO signals (prospect_id, type, evidence, confidence, created_at) "
            "VALUES (?, 'funding', 'verified text', 0.5, ?)",
            (prospect_id, now),
        )
        conn.execute(
            "INSERT INTO signals (prospect_id, type, evidence, confidence, created_at) "
            "VALUES (?, 'funding', 'another verified text', 0.9, ?)",
            (prospect_id, now),
        )
        task_id = db.enqueue_task(conn, batch.SCORE_PROSPECT_TASK, {"prospect_id": prospect_id})
    finally:
        conn.close()

    assert QueueWorker().run_once() == 1
    conn = db.connect()
    try:
        assert db.get_task(conn, task_id)["status"] == "done"
        saved = db.latest_score(conn, prospect_id)
        assert saved["score"] == pytest.approx(74.45)
        assert saved["partial"] == 0
        breakdown = json.loads(saved["breakdown_json"])
        assert breakdown["icp_similarity"] == 1.0
        assert breakdown["signal_score"] == pytest.approx(27.0)
        assert breakdown["size_fit"] == 100.0
        assert breakdown["title_fit"] == 100.0
    finally:
        conn.close()


def test_embed_and_score_uses_test_only_embedding_stub_for_local_inputs(
    db_path, tmp_path, monkeypatch
):
    conn = db.connect()
    try:
        product_id, prospect_id = _product_and_prospect(conn)
        icp_data = {
            "company_size_min": 50,
            "company_size_max": 500,
            "buyer_titles": ["VP of Sales"],
        }
        conn.execute(
            "INSERT INTO icps (product_id, icp_json, embedding, embedding_model, created_at) "
            "VALUES (?, ?, NULL, '', ?)",
            (product_id, json.dumps(icp_data), db.utcnow()),
        )
        conn.execute(
            "INSERT INTO signals (prospect_id, type, evidence, confidence, created_at) "
            "VALUES (?, 'none', '', 0, ?)",
            (prospect_id, db.utcnow()),
        )
        page_dir = tmp_path / "pages"
        prospects.store_prospect_page(
            conn, prospect_id=prospect_id, text="Local prospect page.", page_dir=page_dir
        )
        seen = {}

        def test_embedder(texts, *, model_name):
            seen["texts"] = list(texts)
            seen["model_name"] = model_name
            return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(batch, "embed_texts", test_embedder)
        result = batch.embed_and_score_prospect(conn, prospect_id, page_dir=page_dir)
        icp_row = conn.execute(
            "SELECT embedding, embedding_model FROM icps WHERE product_id = ?", (product_id,)
        ).fetchone()
        prospect_row = db.get_prospect(conn, prospect_id)
        saved = db.latest_score(conn, prospect_id)
        assert seen["texts"] == [
            json.dumps(icp_data, ensure_ascii=False, sort_keys=True),
            "Local prospect page.",
        ]
        assert seen["model_name"] == embeddings.DEFAULT_MODEL
        assert embeddings.unpack_embedding(icp_row["embedding"]) == [1.0, 0.0]
        assert icp_row["embedding_model"] == embeddings.DEFAULT_MODEL
        assert embeddings.unpack_embedding(prospect_row["page_embedding"]) == [1.0, 0.0]
        assert result["score"] == pytest.approx(65.0)
        assert result["partial"] is False
        assert saved["partial"] == 0
    finally:
        conn.close()


def test_missing_embedding_model_leaves_similarity_null_and_score_partial(
    db_path, tmp_path, monkeypatch
):
    conn = db.connect()
    try:
        product_id, prospect_id = _product_and_prospect(conn)
        icp_data = {
            "company_size_min": 50,
            "company_size_max": 500,
            "buyer_titles": ["VP of Sales"],
        }
        conn.execute(
            "INSERT INTO icps (product_id, icp_json, embedding, embedding_model, created_at) "
            "VALUES (?, ?, NULL, '', ?)",
            (product_id, json.dumps(icp_data), db.utcnow()),
        )
        conn.execute(
            "INSERT INTO signals (prospect_id, type, evidence, confidence, created_at) "
            "VALUES (?, 'none', '', 0, ?)",
            (prospect_id, db.utcnow()),
        )
        page_dir = tmp_path / "pages"
        prospects.store_prospect_page(
            conn, prospect_id=prospect_id, text="Local prospect page.", page_dir=page_dir
        )

        def no_cached_model(*args, **kwargs):
            raise EmbeddingModelUnavailable("embedding model is not cached")

        monkeypatch.setattr(batch, "embed_texts", no_cached_model)
        result = batch.embed_and_score_prospect(conn, prospect_id, page_dir=page_dir)
        saved = db.latest_score(conn, prospect_id)
        breakdown = json.loads(saved["breakdown_json"])
        assert result["score"] == pytest.approx(30.0)
        assert result["partial"] is True
        assert breakdown["icp_similarity"] is None
        assert db.get_prospect(conn, prospect_id)["page_embedding"] is None
    finally:
        conn.close()


def test_missing_score_inputs_are_null_and_score_is_partial(db_path):
    conn = db.connect()
    try:
        _, prospect_id = _product_and_prospect(conn)
        result = batch.score_and_store_prospect(conn, prospect_id)
        saved = db.latest_score(conn, prospect_id)
        assert result["score"] == 0.0
        assert result["partial"] is True
        assert saved["score"] == 0.0
        assert saved["partial"] == 1
        breakdown = json.loads(saved["breakdown_json"])
        assert breakdown["icp_similarity"] is None
        assert breakdown["signal_score"] is None
        assert breakdown["size_fit"] is None
        assert breakdown["title_fit"] is None
        assert breakdown["missing_components"] == [
            "icp_similarity", "signal_score", "size_fit", "title_fit"
        ]
        assert set(breakdown["weighted_contributions"].values()) == {0.0}
    finally:
        conn.close()
