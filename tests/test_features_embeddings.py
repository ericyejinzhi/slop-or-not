import numpy as np
import pytest

from sloppy.features import embeddings


class _FakeModel:
    def encode(self, texts, normalize_embeddings, convert_to_numpy):
        assert normalize_embeddings is True
        assert convert_to_numpy is True
        # deterministic fake embedding: one row per text, values based on text length
        return np.array([[float(len(t))] * embeddings.EMBEDDING_DIM for t in texts])


def test_embed_texts_calls_model_with_normalize_and_numpy(monkeypatch):
    monkeypatch.setattr(embeddings, "_load_model", lambda: _FakeModel())

    result = embeddings.embed_texts(["hello", "hi"])

    assert result.shape == (2, embeddings.EMBEDDING_DIM)
    assert result[0, 0] == 5.0  # len("hello")
    assert result[1, 0] == 2.0  # len("hi")


@pytest.mark.slow
def test_embed_texts_real_model_produces_unit_norm_embedding():
    result = embeddings.embed_texts(["hello world"])
    assert result.shape == (1, embeddings.EMBEDDING_DIM)
    norm = np.linalg.norm(result[0])
    assert abs(norm - 1.0) < 1e-4
