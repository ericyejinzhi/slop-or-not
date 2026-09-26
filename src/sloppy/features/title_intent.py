"""Unsupervised title-intent scoring: cosine similarity against small hand-written
prototype sets. Prototype sets are a first draft, flagged for revisit after real labels
exist - same treatment as the Phase 2 rubric.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from sloppy.features.embeddings import embed_texts

PROTOTYPE_TITLES: dict[str, tuple[str, ...]] = {
    "grey_area_lure": (
        "You won't believe what happened next",
        "This changes everything",
        "The one thing nobody tells you about this",
        "Wait until you see what happens at the end",
        "This is why you should never do this again",
        "I can't believe this actually worked",
    ),
    "intentionally_mysterious": (
        "The Man Who Vanished Twice",
        "What Really Happened at Chernobyl",
        "The Last Photograph Ever Taken",
        "A Village With No Name",
        "The Sound No One Could Explain",
        "Inside the Room No One Opens",
    ),
    "transparent": (
        "How to replace a bike chain",
        "Python tutorial for beginners: variables and loops",
        "Full recipe: homemade sourdough bread",
        "Review: the new phone's camera explained",
        "Step-by-step guide to filing taxes online",
        "Explaining the 2024 election results",
    ),
}


@dataclass
class TitleIntentScores:
    lure_score: float
    mysterious_score: float
    transparent_score: float


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


@lru_cache
def _prototype_centroids() -> dict[str, tuple[float, ...]]:
    """One centroid per category: normalize each prototype embedding, average, then
    re-normalize. More robust to any single prototype's wording quirks than
    max-similarity (oversensitive to one phrase) or mean-of-pairwise (equivalent but 3x
    more expensive to compute). Returned as tuples (not ndarrays) so this stays hashable
    for lru_cache and the result is safe to reuse without accidental in-place mutation.
    """
    centroids = {}
    for category, titles in PROTOTYPE_TITLES.items():
        vectors = embed_texts(list(titles))
        normalized = np.array([_normalize(v) for v in vectors])
        centroid = _normalize(normalized.mean(axis=0))
        centroids[category] = tuple(float(x) for x in centroid)
    return centroids


def score_title_intent(title: str) -> TitleIntentScores:
    title_vec = _normalize(embed_texts([title])[0])
    centroids = _prototype_centroids()
    scores = {
        category: float(np.dot(title_vec, np.array(centroid)))
        for category, centroid in centroids.items()
    }
    return TitleIntentScores(
        lure_score=scores["grey_area_lure"],
        mysterious_score=scores["intentionally_mysterious"],
        transparent_score=scores["transparent"],
    )
