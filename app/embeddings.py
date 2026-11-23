"""Real, local-only sentence embeddings with a lazy model cache.

The model downloads from Hugging Face Hub only when it is not already cached.
After the first successful download, set ``HF_HUB_OFFLINE=1`` to ensure loading
and inference use the local cache without Hub access. This module never uses an
LLM or a hosted inference endpoint.
"""

from __future__ import annotations

import math
import struct
import threading
from collections.abc import Sequence
from typing import Any

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL = DEFAULT_MODEL
_EMBEDDING_MAGIC = b"HE01"
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


class EmbeddingError(RuntimeError):
    """Base error for local embedding operations."""


class EmbeddingModelUnavailable(EmbeddingError):
    """The model or its required files are not available locally."""


def _load_model(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingModelUnavailable(
            "sentence-transformers is not installed; install the project dependencies first"
        ) from exc
    try:
        return SentenceTransformer(model_name)
    except Exception as exc:
        raise EmbeddingModelUnavailable(
            f"Could not load local embedding model {model_name!r}. "
            "Download it once while online, then retry with HF_HUB_OFFLINE=1. "
            f"Cause: {exc}"
        ) from exc


def _get_model(model_name: str) -> Any:
    model = _MODEL_CACHE.get(model_name)
    if model is not None:
        return model
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(model_name)
        if model is None:
            model = _load_model(model_name)
            _MODEL_CACHE[model_name] = model
    return model


def embed_texts(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> list[list[float]]:
    """Encode text locally and return normalized vectors as plain Python floats."""
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("model_name must be a non-empty string")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if isinstance(texts, (str, bytes)):
        raise TypeError("texts must be a sequence of strings, not a single string")
    inputs = list(texts)
    if not inputs:
        return []
    if any(not isinstance(text, str) for text in inputs):
        raise TypeError("every input to embed_texts must be a string")

    model = _get_model(model_name.strip())
    try:
        encoded = model.encode(
            inputs,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
    except Exception as exc:
        raise EmbeddingError(f"Local embedding failed for {model_name!r}: {exc}") from exc

    try:
        rows = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        if len(inputs) == 1 and rows and isinstance(rows[0], (int, float)):
            rows = [rows]
        vectors = [[float(value) for value in row] for row in rows]
    except (TypeError, ValueError, OverflowError) as exc:
        raise EmbeddingError("Embedding model returned a non-numeric result") from exc
    if len(vectors) != len(inputs):
        raise EmbeddingError(
            f"Embedding model returned {len(vectors)} vectors for {len(inputs)} inputs"
        )
    if not vectors or any(not vector for vector in vectors):
        raise EmbeddingError("Embedding model returned an empty vector")
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise EmbeddingError("Embedding model returned vectors with inconsistent dimensions")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise EmbeddingError("Embedding model returned a non-finite value")
    return vectors


def embed_text(text: str, *, model_name: str = DEFAULT_MODEL) -> list[float]:
    """Convenience wrapper to embed one string."""
    return embed_texts([text], model_name=model_name)[0]


def pack_embedding(vector: Sequence[float]) -> bytes:
    """Serialize a non-empty vector as a versioned little-endian float32 BLOB."""
    if isinstance(vector, (str, bytes)):
        raise TypeError("vector must be a sequence of numeric values")
    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("vector must contain numeric values") from exc
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("vector must contain finite numeric values")
    try:
        return _EMBEDDING_MAGIC + struct.pack("<I", len(values)) + struct.pack(
            f"<{len(values)}f", *values
        )
    except (OverflowError, struct.error) as exc:
        raise ValueError("vector values cannot be represented as float32") from exc


def unpack_embedding(blob: bytes | bytearray | memoryview | None) -> list[float] | None:
    """Decode a BLOB written by :func:`pack_embedding`; ``None`` stays missing."""
    if blob is None:
        return None
    raw = bytes(blob)
    header_size = len(_EMBEDDING_MAGIC) + 4
    if len(raw) < header_size or raw[: len(_EMBEDDING_MAGIC)] != _EMBEDDING_MAGIC:
        raise ValueError("embedding BLOB has an unsupported format")
    dimensions = struct.unpack("<I", raw[len(_EMBEDDING_MAGIC) : header_size])[0]
    expected_size = header_size + dimensions * 4
    if dimensions == 0 or len(raw) != expected_size:
        raise ValueError("embedding BLOB has an invalid size")
    values = list(struct.unpack(f"<{dimensions}f", raw[header_size:]))
    if any(not math.isfinite(value) for value in values):
        raise ValueError("embedding BLOB contains a non-finite value")
    return values
