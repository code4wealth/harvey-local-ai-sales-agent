from __future__ import annotations

import math

import pytest

from app import embeddings


class StubSentenceTransformer:
    """Test-only embedding stub; the app module always loads the real model."""

    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        vectors = {
            "first": [0.6, 0.8],
            "second": [1.0, 0.0],
        }
        return [vectors[text] for text in texts]


def test_embed_texts_uses_normalized_local_model_and_caches_it(monkeypatch):
    model = StubSentenceTransformer()
    loaded = []
    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {})
    monkeypatch.setattr(embeddings, "_load_model", lambda name: loaded.append(name) or model)

    first = embeddings.embed_texts(["first", "second"])
    second = embeddings.embed_text("first")

    assert loaded == [embeddings.DEFAULT_MODEL]
    assert first == [[0.6, 0.8], [1.0, 0.0]]
    assert second == [0.6, 0.8]
    assert model.calls[0][1] == {
        "batch_size": 32,
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "normalize_embeddings": True,
    }
    assert math.sqrt(sum(value * value for value in first[0])) == pytest.approx(1.0)


def test_embed_texts_empty_input_needs_no_model(monkeypatch):
    monkeypatch.setattr(
        embeddings, "_load_model", lambda _: pytest.fail("empty input should not load a model")
    )
    assert embeddings.embed_texts([]) == []


@pytest.mark.parametrize(
    ("texts", "kwargs", "error"),
    [
        ("single string", {}, TypeError),
        (["ok", 2], {}, TypeError),
        (["ok"], {"batch_size": 0}, ValueError),
        (["ok"], {"model_name": " "}, ValueError),
    ],
)
def test_embed_texts_validates_inputs(texts, kwargs, error):
    with pytest.raises(error):
        embeddings.embed_texts(texts, **kwargs)


def test_pack_unpack_embedding_round_trip_and_rejects_corruption():
    packed = embeddings.pack_embedding([0.25, -0.5, 1.0])
    unpacked = embeddings.unpack_embedding(packed)
    assert unpacked == pytest.approx([0.25, -0.5, 1.0])
    assert embeddings.unpack_embedding(None) is None
    with pytest.raises(ValueError, match="unsupported format"):
        embeddings.unpack_embedding(b"not-an-embedding")
    with pytest.raises(ValueError, match="invalid size"):
        embeddings.unpack_embedding(b"HE01\x02\x00\x00\x00\x00")
