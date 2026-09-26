import numpy as np
import pytest

from sloppy.features import title_intent
from sloppy.features.title_intent import PROTOTYPE_TITLES, score_title_intent


def _fake_embed_factory(vectors_by_text: dict[str, np.ndarray], default: np.ndarray):
    def _fake_embed(texts: list[str]) -> np.ndarray:
        return np.array([vectors_by_text.get(t, default) for t in texts])

    return _fake_embed


def test_score_title_intent_cosine_math_against_fixed_fake_vectors(monkeypatch):
    """Pure cosine-similarity math, no real model - every prototype in a category maps
    to the same fixed unit vector, and the title exactly matches one category's axis, so
    the expected scores are exact: 1.0 for the matching category, 0.0 for the orthogonal
    ones."""
    title_intent._prototype_centroids.cache_clear()

    axis_lure = np.array([1.0, 0.0, 0.0])
    axis_mysterious = np.array([0.0, 1.0, 0.0])
    axis_transparent = np.array([0.0, 0.0, 1.0])

    vectors_by_text = {}
    for title in PROTOTYPE_TITLES["grey_area_lure"]:
        vectors_by_text[title] = axis_lure
    for title in PROTOTYPE_TITLES["intentionally_mysterious"]:
        vectors_by_text[title] = axis_mysterious
    for title in PROTOTYPE_TITLES["transparent"]:
        vectors_by_text[title] = axis_transparent
    vectors_by_text["a lure-axis title"] = axis_lure

    fake_embed = _fake_embed_factory(vectors_by_text, default=axis_lure)
    monkeypatch.setattr(title_intent, "embed_texts", fake_embed)

    try:
        scores = score_title_intent("a lure-axis title")
        assert scores.lure_score == pytest.approx(1.0)
        assert scores.mysterious_score == pytest.approx(0.0, abs=1e-9)
        assert scores.transparent_score == pytest.approx(0.0, abs=1e-9)
    finally:
        title_intent._prototype_centroids.cache_clear()


@pytest.mark.slow
def test_score_title_intent_real_model_ranks_titles_correctly():
    title_intent._prototype_centroids.cache_clear()
    try:
        transparent = score_title_intent("How to replace a bike chain")
        lure = score_title_intent("You won't believe what happened next")

        assert transparent.transparent_score > transparent.lure_score
        assert transparent.transparent_score > transparent.mysterious_score
        assert lure.lure_score > lure.transparent_score
    finally:
        title_intent._prototype_centroids.cache_clear()
