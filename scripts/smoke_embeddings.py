#!/usr/bin/env python3
"""Load the real, cached sentence-embedding model and verify two vectors.

Pre-cache the model while online by constructing SentenceTransformer directly;
the application loader sets HF_HUB_OFFLINE=1 before loading and never downloads
model files. After the cache is populated, verify it offline with:
    HF_HUB_OFFLINE=1 python scripts/smoke_embeddings.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.embeddings import DEFAULT_MODEL, EmbeddingError, _get_model, embed_texts
from app.scoring import cosine_similarity


SAMPLE_TEXTS = (
    "A small engineering team builds workflow software for logistics operations.",
    "Logistics teams use software to coordinate operational workflows.",
)


def main() -> int:
    offline = os.environ.get("HF_HUB_OFFLINE", "0")
    print(f"Embedding model: {DEFAULT_MODEL}")
    print(f"HF_HUB_OFFLINE: {offline}")
    try:
        model = _get_model(DEFAULT_MODEL)
        max_seq_length = model.max_seq_length
        vectors = embed_texts(SAMPLE_TEXTS)
    except EmbeddingError as exc:
        print(f"Embedding smoke test failed: {exc}", file=sys.stderr)
        return 1
    if len(vectors) != len(SAMPLE_TEXTS) or not vectors[0]:
        print("Embedding smoke test failed: unexpected vector shape", file=sys.stderr)
        return 1
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        print("Embedding smoke test failed: vector dimensions differ", file=sys.stderr)
        return 1
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        print("Embedding smoke test failed: vector contains non-finite values", file=sys.stderr)
        return 1
    norms = [math.sqrt(sum(value * value for value in vector)) for vector in vectors]
    if any(not math.isclose(value, 1.0, rel_tol=1e-3, abs_tol=1e-3) for value in norms):
        print("Embedding smoke test failed: vectors are not normalized", file=sys.stderr)
        return 1
    similarity = cosine_similarity(vectors[0], vectors[1])
    if similarity is None:
        print("Embedding smoke test failed: cosine similarity is unavailable", file=sys.stderr)
        return 1
    print(f"Model max_seq_length: {max_seq_length}")
    print(f"Vector count: {len(vectors)}")
    print(f"Vector dimension: {dimensions}")
    print(f"First vector norm: {norms[0]:.6f}")
    print(f"Cosine similarity: {similarity:.6f}")
    print("PASS: local embeddings are available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
