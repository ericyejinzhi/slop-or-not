"""Comment topic clustering: pure numpy/sklearn, zero model-loading of its own. Caller
supplies precomputed embeddings (features/embeddings.py) and sentiments
(features/sentiment.py) - both already computed for other purposes, reused here.
"""

from dataclasses import dataclass
from statistics import pstdev

import numpy as np
from sklearn.cluster import KMeans

TOPIC_K = 5
MIN_COMMENTS_FOR_CLUSTERING = TOPIC_K


@dataclass
class TopicAggregate:
    topic_cluster_count: int | None
    topic_top_cluster_share: float | None
    topic_top_cluster_sentiment: float | None
    topic_sentiment_spread: float | None


def cluster_comment_topics(embeddings: np.ndarray, sentiments: list[float]) -> TopicAggregate:
    """Returns all-None if fewer than MIN_COMMENTS_FOR_CLUSTERING comments - KMeans
    degenerates below that many points for k=TOPIC_K clusters, and the aggregates
    wouldn't be meaningful.

    topic_sentiment_spread is the std of per-cluster MEAN sentiment - the "narrow vs.
    spread" signal the roadmap names (slop draws a narrow, repetitive comment
    distribution; genuine content spreads across topics with more varied reactions).
    """
    n = len(sentiments)
    if n < MIN_COMMENTS_FOR_CLUSTERING:
        return TopicAggregate(None, None, None, None)

    labels = KMeans(n_clusters=TOPIC_K, n_init="auto", random_state=42).fit_predict(embeddings)
    sentiments_arr = np.array(sentiments)

    cluster_sizes = np.bincount(labels, minlength=TOPIC_K)
    top_cluster = int(np.argmax(cluster_sizes))
    top_cluster_mask = labels == top_cluster

    per_cluster_means = [
        float(sentiments_arr[labels == cluster].mean())
        for cluster in range(TOPIC_K)
        if cluster_sizes[cluster] > 0
    ]

    return TopicAggregate(
        topic_cluster_count=int(np.count_nonzero(cluster_sizes)),
        topic_top_cluster_share=float(cluster_sizes[top_cluster] / n),
        topic_top_cluster_sentiment=float(sentiments_arr[top_cluster_mask].mean()),
        topic_sentiment_spread=pstdev(per_cluster_means) if len(per_cluster_means) > 1 else 0.0,
    )
