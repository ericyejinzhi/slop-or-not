"""Tests scripts/shap_interaction_report.py's pure extraction function only - the
script's main() (loading a real model artifact, running shap.TreeExplainer against a
real dataset) is a manual, one-off, real-data step with nothing to unit test yet.

scripts/ is deliberately not a package under src/sloppy (see the script's own
docstring), so it isn't import-path-visible to the installed "sloppy" package. Insert
it onto sys.path directly, matching a plain standalone-script's usual test setup.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from shap_interaction_report import top_interaction_pairs  # noqa: E402


def test_top_interaction_pairs_ranks_by_mean_abs_interaction():
    # 3 features, 2 samples, symmetric interaction matrices with a known off-diagonal
    # ranking: (b, c) = 3 > (a, c) = 2 > (a, b) = 1. Diagonal values are main effects,
    # not interactions, and must be excluded from the ranking.
    sample = np.array(
        [
            [9.0, 1.0, 2.0],
            [1.0, 9.0, 3.0],
            [2.0, 3.0, 9.0],
        ]
    )
    interaction_values = np.stack([sample, sample])
    feature_names = ["a", "b", "c"]

    pairs = top_interaction_pairs(interaction_values, feature_names, n=2)

    assert pairs == [("b", "c", 3.0), ("a", "c", 2.0)]


def test_top_interaction_pairs_averages_across_samples():
    sample1 = np.array([[0.0, 4.0], [4.0, 0.0]])
    sample2 = np.array([[0.0, 2.0], [2.0, 0.0]])
    interaction_values = np.stack([sample1, sample2])
    feature_names = ["x", "y"]

    pairs = top_interaction_pairs(interaction_values, feature_names, n=5)

    assert pairs == [("x", "y", 3.0)]


def test_top_interaction_pairs_respects_n():
    n_features = 5
    interaction_values = np.abs(np.random.default_rng(0).normal(size=(4, n_features, n_features)))
    feature_names = [f"f{i}" for i in range(n_features)]

    pairs = top_interaction_pairs(interaction_values, feature_names, n=3)

    assert len(pairs) == 3
    scores = [score for _, _, score in pairs]
    assert scores == sorted(scores, reverse=True)
