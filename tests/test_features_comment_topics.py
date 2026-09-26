import math

import numpy as np
import pytest

from sloppy.features.comment_topics import (
    MIN_COMMENTS_FOR_CLUSTERING,
    TOPIC_K,
    cluster_comment_topics,
)


def test_cluster_comment_topics_returns_all_none_below_minimum():
    embeddings = np.random.rand(MIN_COMMENTS_FOR_CLUSTERING - 1, 8)
    sentiments = [0.1] * (MIN_COMMENTS_FOR_CLUSTERING - 1)

    result = cluster_comment_topics(embeddings, sentiments)

    assert result.topic_cluster_count is None
    assert result.topic_top_cluster_share is None
    assert result.topic_top_cluster_sentiment is None
    assert result.topic_sentiment_spread is None


def test_cluster_comment_topics_five_maximally_separated_singletons():
    # 5 points at distinct one-hot-like locations in 5D, maximally separated - with
    # k=5 clusters requested, KMeans assigns each point its own singleton cluster
    # regardless of internal label ordering, making every aggregate exactly predictable.
    embeddings = np.eye(TOPIC_K) * 100  # scaled up so separation is unambiguous
    sentiments = [1.0, -1.0, 0.5, -0.5, 0.0]

    result = cluster_comment_topics(embeddings, sentiments)

    assert result.topic_cluster_count == TOPIC_K
    assert result.topic_top_cluster_share == 1 / TOPIC_K  # all 5 clusters tied at size 1
    # the winning cluster's sentiment is exactly one of the 5 singleton values, whichever
    # KMeans happens to label as cluster 0's argmax winner (tie-broken by label order)
    assert result.topic_top_cluster_sentiment in sentiments
    # per-cluster means = the 5 sentiment values themselves (order-independent pstdev)
    expected_spread = math.sqrt(sum((s - 0.0) ** 2 for s in sentiments) / len(sentiments))
    assert result.topic_sentiment_spread == pytest.approx(expected_spread, abs=1e-9)


def test_cluster_comment_topics_narrow_distribution_has_low_spread():
    # All comments cluster tightly together in embedding space AND have near-identical
    # sentiment - a "narrow, repetitive" comment section, the slop signal the roadmap
    # names. Spread across clusters should be near zero since every cluster (however
    # KMeans splits this tight blob) has almost the same mean sentiment.
    rng = np.random.default_rng(0)
    embeddings = rng.normal(loc=0.0, scale=0.01, size=(20, 8))
    sentiments = [0.5 + rng.normal(scale=0.001) for _ in range(20)]

    result = cluster_comment_topics(embeddings, sentiments)

    assert result.topic_sentiment_spread is not None
    assert result.topic_sentiment_spread < 0.05
