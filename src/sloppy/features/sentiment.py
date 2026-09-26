"""Comment sentiment: pretrained transformer -> per-comment scores -> per-video/channel
aggregates. aggregate_sentiment/channel_sentiment_rollup take precomputed scores (not a
model), so they're pure and fast to test; score_comments is the only piece that touches
the real model.
"""

from dataclasses import dataclass
from functools import lru_cache
from statistics import mean, pstdev

from transformers import pipeline

SENTIMENT_MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# Deliberately simple, hand-curated - same treatment as features/text.py's clickbait
# lexicon. Revisit once real comment data + error analysis show what's actually useful.
SLOP_KEYWORDS = ("ai slop", "bot", "farm", "reused content", "recycled", "clickbait")


@lru_cache
def _load_pipeline():
    return pipeline("sentiment-analysis", model=SENTIMENT_MODEL_NAME, top_k=None)


def score_comments(texts: list[str]) -> list[float]:
    """Returns P(positive) - P(negative) per text, in [-1, 1]. The cardiffnlp checkpoint
    returns 3-way labels (negative/neutral/positive); neutral is dropped from the
    subtraction, so a comment scored mostly "neutral" naturally lands near 0."""
    if not texts:
        return []
    pipe = _load_pipeline()
    results = pipe(texts)
    scores = []
    for result in results:
        by_label = {item["label"].lower(): item["score"] for item in result}
        scores.append(by_label.get("positive", 0.0) - by_label.get("negative", 0.0))
    return scores


@dataclass
class SentimentAggregate:
    sentiment_mean: float | None
    sentiment_std: float | None
    sentiment_negative_share: float | None
    slop_keyword_rate: float | None
    comment_count_scored: int


def aggregate_sentiment(texts: list[str], scores: list[float]) -> SentimentAggregate:
    if not scores:
        return SentimentAggregate(None, None, None, None, comment_count_scored=0)

    negative_share = sum(1 for s in scores if s < 0) / len(scores)
    keyword_hits = sum(
        1 for text in texts if any(keyword in text.lower() for keyword in SLOP_KEYWORDS)
    )
    return SentimentAggregate(
        sentiment_mean=mean(scores),
        sentiment_std=pstdev(scores) if len(scores) > 1 else 0.0,
        sentiment_negative_share=negative_share,
        slop_keyword_rate=keyword_hits / len(texts) if texts else 0.0,
        comment_count_scored=len(scores),
    )


def channel_sentiment_rollup(
    video_means: dict[str, float], channel_by_video: dict[str, str]
) -> dict[str, float]:
    """channel_id -> mean of that channel's videos' sentiment_mean values."""
    by_channel: dict[str, list[float]] = {}
    for video_id, sentiment in video_means.items():
        channel_id = channel_by_video.get(video_id)
        if channel_id is not None:
            by_channel.setdefault(channel_id, []).append(sentiment)
    return {channel_id: mean(values) for channel_id, values in by_channel.items()}
