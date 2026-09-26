"""Shared sentence-embedding wrapper (sentence-transformers). Model loaded once per
process via lru_cache, mirroring db/session.py's get_engine() pattern.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@lru_cache
def _load_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Returns an (n, 384) array, L2-normalized (so cosine similarity is a plain dot
    product downstream)."""
    model = _load_model()
    return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
