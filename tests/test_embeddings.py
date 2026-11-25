from __future__ import annotations

import math
import os
import sys
from types import ModuleType

import pytest

from app import embeddings
from scripts import smoke_embeddings


class StubSentenceTransformer:
    """Test-only embedding stub; the app module always loads the real model."""

    def __init__(self):
        self.calls = []
        self.max_seq_length = 256

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        vectors = {
            "first": [0.6, 0.8],
            "second": [1.0, 0.0],
            "left": [1.0, 0.0],
        }
        return [vectors.get(text, [0.0, 1.0]) for text in texts]


def test_local_model_cache_status_detects_huggingface_snapshot_without_loading(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "hf-cache"
    snapshot = (
        cache_root
        / "models--sentence-transformers--all-MiniLM-L6-v2"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "pytorch_model.bin").write_bytes(b"local model")
    monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_CACHE", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {})

    status = embeddings.local_model_cache_status()

    assert status == {
        "model": embeddings.DEFAULT_MODEL,
        "available": True,
        "loaded": False,
        "cached": True,
    }


def test_local_model_cache_status_reports_missing_files_and_loaded_model(
    tmp_path, monkeypatch
):
    cache_root = tmp_path / "hf-cache"
    snapshot = (
        cache_root
        / "models--sentence-transformers--all-MiniLM-L6-v2"
        / "snapshots"
        / "incomplete"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HF_HUB_CACHE", str(cache_root))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_CACHE", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {})

    assert embeddings.local_model_cache_status()["available"] is False

    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {embeddings.DEFAULT_MODEL: object()})
    status = embeddings.local_model_cache_status()
    assert status["available"] is True
    assert status["loaded"] is True
    assert status["cached"] is False


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


def test_model_load_forces_hugging_face_and_transformers_offline(monkeypatch):
    observed = {}

    class LocalOnlyModel:
        def __init__(self, model_name):
            observed["model_name"] = model_name
            observed["hf_offline"] = os.environ.get("HF_HUB_OFFLINE")
            observed["transformers_offline"] = os.environ.get("TRANSFORMERS_OFFLINE")

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = LocalOnlyModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")

    model = embeddings._load_model(embeddings.DEFAULT_MODEL)

    assert isinstance(model, LocalOnlyModel)
    assert observed == {
        "model_name": embeddings.DEFAULT_MODEL,
        "hf_offline": "1",
        "transformers_offline": "1",
    }


def test_offline_strict_forces_cache_only_model_loading_and_disables_telemetry(monkeypatch):
    observed = {}

    class LocalOnlyModel:
        def __init__(self, model_name):
            observed["model_name"] = model_name
            observed["hf_offline"] = os.environ.get("HF_HUB_OFFLINE")
            observed["transformers_offline"] = os.environ.get("TRANSFORMERS_OFFLINE")
            observed["hub_telemetry"] = os.environ.get("HF_HUB_DISABLE_TELEMETRY")
            observed["implicit_token"] = os.environ.get("HF_HUB_DISABLE_IMPLICIT_TOKEN")

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = LocalOnlyModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setenv("OFFLINE_STRICT", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "0")
    monkeypatch.setenv("HF_HUB_DISABLE_IMPLICIT_TOKEN", "0")

    embeddings._load_model(embeddings.DEFAULT_MODEL)

    assert observed == {
        "model_name": embeddings.DEFAULT_MODEL,
        "hf_offline": "1",
        "transformers_offline": "1",
        "hub_telemetry": "1",
        "implicit_token": "1",
    }


def test_embed_long_text_chunks_averages_normalizes_and_caps_at_six(monkeypatch):
    model = StubSentenceTransformer()
    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {})
    monkeypatch.setattr(embeddings, "_load_model", lambda _: model)

    text = "left " + ("x" * 800) + " right"
    vector = embeddings.embed_long_text(text)

    chunks = model.calls[0][0]
    assert chunks == ["left", "x" * 800, "right"]
    assert vector == pytest.approx([1 / math.sqrt(5), 2 / math.sqrt(5)])
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)

    too_many_chunks = " ".join(f"word{index}" + ("x" * 800) for index in range(8))
    embeddings.embed_long_text(too_many_chunks)
    assert len(model.calls[1][0]) == embeddings.MAX_LONG_TEXT_CHUNKS == 6


def test_embed_long_text_rejects_non_string_input():
    with pytest.raises(TypeError, match="text must be a string"):
        embeddings.embed_long_text(42)


def test_embedding_smoke_reports_model_sequence_limit_and_dimension(monkeypatch, capsys):
    model = StubSentenceTransformer()
    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {})
    monkeypatch.setattr(embeddings, "_load_model", lambda _: model)

    assert smoke_embeddings.main() == 0
    output = capsys.readouterr().out
    assert "Model max_seq_length: 256" in output
    assert "Vector dimension: 2" in output


def test_failed_model_load_is_retried_instead_of_cached(monkeypatch):
    calls = []

    def fail_to_load(model_name):
        calls.append(model_name)
        raise embeddings.EmbeddingModelUnavailable("model files unavailable")

    monkeypatch.setattr(embeddings, "_MODEL_CACHE", {})
    monkeypatch.setattr(embeddings, "_load_model", fail_to_load)
    for _ in range(2):
        with pytest.raises(embeddings.EmbeddingModelUnavailable):
            embeddings.embed_texts(["retry me"])

    assert calls == [embeddings.DEFAULT_MODEL, embeddings.DEFAULT_MODEL]
    assert embeddings._MODEL_CACHE == {}


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
