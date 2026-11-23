"""Deterministic queue handlers; none of these tasks calls an LLM."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app import db, scoring
from app.embeddings import (
    DEFAULT_MODEL,
    EmbeddingError,
    embed_texts,
    pack_embedding,
    unpack_embedding,
)
from app.prospects import (
    ProspectPageError,
    import_prospects_csv,
    load_prospect_page,
)
from app.queue_worker import HANDLERS, register_handler

logger = logging.getLogger("harvey.batch")

IMPORT_PROSPECTS_TASK = "prospects.import_csv"
SCORE_PROSPECT_TASK = "prospects.score"


def _handle_import_prospects(payload: dict[str, Any]) -> None:
    try:
        product_id = int(payload["product_id"])
        csv_text = payload["csv_text"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("prospects.import_csv requires product_id and csv_text") from exc
    if not isinstance(csv_text, str):
        raise ValueError("csv_text must be a string")
    conn = db.connect()
    try:
        import_prospects_csv(conn, product_id=product_id, csv_text=csv_text)
    finally:
        conn.close()


def _latest_rows(conn, prospect_id: int, product_id: int):
    icp = conn.execute(
        "SELECT id, icp_json, embedding, embedding_model FROM icps "
        "WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (product_id,),
    ).fetchone()
    research = conn.execute(
        "SELECT embedding, embedding_model, icp_similarity FROM prospect_research "
        "WHERE prospect_id = ? ORDER BY id DESC LIMIT 1",
        (prospect_id,),
    ).fetchone()
    signals = list(
        conn.execute(
            "SELECT type, confidence FROM signals WHERE prospect_id = ? ORDER BY id",
            (prospect_id,),
        ).fetchall()
    )
    return icp, research, signals


def _unpack_or_none(blob: bytes | None) -> list[float] | None:
    try:
        return unpack_embedding(blob)
    except (TypeError, ValueError):
        return None


def _icp_data(icp) -> Mapping[str, Any]:
    if icp is None:
        return {}
    try:
        parsed = json.loads(icp["icp_json"])
    except (TypeError, json.JSONDecodeError):
        return {}
    if isinstance(parsed, Mapping):
        return parsed
    if parsed is not None:
        logger.warning("ignoring non-object ICP JSON for product_id=%s", icp["id"])
    return {}


def score_and_store_prospect(conn, prospect_id: int) -> dict[str, Any]:
    """Score only persisted inputs; missing data stays null and sets ``partial``."""
    prospect = db.get_prospect(conn, prospect_id)
    if prospect is None:
        raise ValueError(f"prospect {prospect_id} not found")
    icp, research, signals = _latest_rows(
        conn, prospect_id=int(prospect_id), product_id=prospect["product_id"]
    )
    icp_data = _icp_data(icp)

    similarity = None
    if icp is not None:
        icp_vector = _unpack_or_none(icp["embedding"])
        icp_model = icp["embedding_model"]
        prospect_vectors: list[tuple[list[float] | None, str]] = [
            (_unpack_or_none(prospect["page_embedding"]), prospect["page_embedding_model"])
        ]
        if research is not None:
            prospect_vectors.append(
                (_unpack_or_none(research["embedding"]), research["embedding_model"])
            )
        if icp_vector is not None and icp_model:
            for vector, model in prospect_vectors:
                if vector is not None and model == icp_model:
                    similarity = scoring.icp_similarity(icp_vector, vector)
                    break
        if similarity is None and research is not None:
            # This field stores the normalized 0–1 component, never raw cosine.
            similarity = research["icp_similarity"]

    raw_signals = [dict(row) for row in signals] if signals else None
    size_range = {
        "min": icp_data.get("company_size_min"),
        "max": icp_data.get("company_size_max"),
    }
    buyer_titles = icp_data.get("buyer_titles")
    result = scoring.score_prospect(
        icp_similarity=similarity,
        signal_score=scoring.signal_score(raw_signals),
        size_fit=scoring.size_fit(prospect["employee_count"], size_range),
        title_fit=scoring.title_fit(
            prospect["contact_title"], buyer_titles if isinstance(buyer_titles, list) else None
        ),
    )
    db.save_score(
        conn,
        prospect_id=prospect_id,
        score=result["score"],
        breakdown=result["breakdown"],
        partial=result["partial"],
    )
    conn.commit()
    return result


def embed_and_score_prospect(
    conn,
    prospect_id: int,
    *,
    page_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Embed available persisted ICP/page text locally, then save a score.

    If the model/cache or page text is unavailable, embedding similarity remains
    null and the normal partial-score rules apply. No summary or other input is
    generated to fill the gap.
    """
    prospect = db.get_prospect(conn, prospect_id)
    if prospect is None:
        raise ValueError(f"prospect {prospect_id} not found")
    icp = conn.execute(
        "SELECT id, icp_json, embedding, embedding_model FROM icps "
        "WHERE product_id = ? ORDER BY id DESC LIMIT 1",
        (prospect["product_id"],),
    ).fetchone()
    if icp is None:
        return score_and_store_prospect(conn, prospect_id)

    icp_data = _icp_data(icp)
    icp_vector = _unpack_or_none(icp["embedding"])
    page_vector = _unpack_or_none(prospect["page_embedding"])
    icp_text = json.dumps(icp_data, ensure_ascii=False, sort_keys=True) if icp_data else ""
    needs_icp = bool(icp_text) and (
        icp_vector is None or icp["embedding_model"] != DEFAULT_MODEL
    )
    needs_page = bool(prospect["page_text_path"]) and (
        page_vector is None or prospect["page_embedding_model"] != DEFAULT_MODEL
    )
    page_text = ""
    if needs_page:
        try:
            page_text = load_prospect_page(conn, prospect_id, page_dir=page_dir)
        except (FileNotFoundError, ProspectPageError) as exc:
            logger.info("local page text unavailable for prospect_id=%s: %s", prospect_id, exc)
        needs_page = bool(page_text.strip())

    texts: list[str] = []
    icp_index: int | None = None
    page_index: int | None = None
    if needs_icp:
        icp_index = len(texts)
        texts.append(icp_text)
    if needs_page:
        page_index = len(texts)
        texts.append(page_text)

    if texts:
        try:
            vectors = embed_texts(texts, model_name=DEFAULT_MODEL)
        except EmbeddingError as exc:
            logger.warning("local embeddings unavailable; score will be partial: %s", exc)
        else:
            if icp_index is not None:
                icp_vector = vectors[icp_index]
                conn.execute(
                    "UPDATE icps SET embedding = ?, embedding_model = ? WHERE id = ?",
                    (pack_embedding(icp_vector), DEFAULT_MODEL, icp["id"]),
                )
            if page_index is not None:
                page_vector = vectors[page_index]
                conn.execute(
                    "UPDATE prospects SET page_embedding = ?, page_embedding_model = ? "
                    "WHERE id = ?",
                    (pack_embedding(page_vector), DEFAULT_MODEL, prospect_id),
                )
            conn.commit()
    return score_and_store_prospect(conn, prospect_id)


def _handle_score_prospect(payload: dict[str, Any]) -> None:
    try:
        prospect_id = int(payload["prospect_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("prospects.score requires prospect_id") from exc
    conn = db.connect()
    try:
        embed_and_score_prospect(conn, prospect_id)
    finally:
        conn.close()


def register_batch_handlers() -> None:
    """Register local deterministic handlers once per process."""
    if IMPORT_PROSPECTS_TASK not in HANDLERS:
        register_handler(
            IMPORT_PROSPECTS_TASK, _handle_import_prospects, requires_ollama=False
        )
    if SCORE_PROSPECT_TASK not in HANDLERS:
        register_handler(SCORE_PROSPECT_TASK, _handle_score_prospect, requires_ollama=False)
