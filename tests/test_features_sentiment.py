import pytest

from sloppy.features.sentiment import aggregate_sentiment, channel_sentiment_rollup, score_comments


def test_aggregate_sentiment_computes_mean_std_and_negative_share():
    texts = ["great video", "terrible video", "okay video"]
    scores = [0.8, -0.6, 0.1]

    agg = aggregate_sentiment(texts, scores)

    assert agg.sentiment_mean == pytest.approx((0.8 - 0.6 + 0.1) / 3)
    assert agg.sentiment_negative_share == pytest.approx(1 / 3)
    assert agg.comment_count_scored == 3
    assert agg.sentiment_std is not None


def test_aggregate_sentiment_empty_returns_all_none():
    agg = aggregate_sentiment([], [])
    assert agg.sentiment_mean is None
    assert agg.sentiment_std is None
    assert agg.sentiment_negative_share is None
    assert agg.slop_keyword_rate is None
    assert agg.comment_count_scored == 0


def test_aggregate_sentiment_single_comment_std_is_zero():
    agg = aggregate_sentiment(["fine"], [0.2])
    assert agg.sentiment_std == 0.0


def test_aggregate_sentiment_detects_slop_keywords():
    texts = ["this is clearly a bot farm", "genuinely great content", "reused content again"]
    scores = [0.0, 0.5, -0.2]

    agg = aggregate_sentiment(texts, scores)

    assert agg.slop_keyword_rate == pytest.approx(
        2 / 3
    )  # "bot"/"farm" in text 1, "reused content" in text 3


def test_channel_sentiment_rollup_averages_per_channel():
    video_means = {"v1": 0.5, "v2": -0.5, "v3": 1.0}
    channel_by_video = {"v1": "c1", "v2": "c1", "v3": "c2"}

    rollup = channel_sentiment_rollup(video_means, channel_by_video)

    assert rollup["c1"] == pytest.approx(0.0)  # mean(0.5, -0.5)
    assert rollup["c2"] == pytest.approx(1.0)


def test_channel_sentiment_rollup_ignores_videos_with_unknown_channel():
    video_means = {"v1": 0.5, "orphan": 99.0}
    channel_by_video = {"v1": "c1"}

    rollup = channel_sentiment_rollup(video_means, channel_by_video)

    assert rollup == {"c1": pytest.approx(0.5)}


def test_score_comments_empty_list_returns_empty():
    assert score_comments([]) == []


@pytest.mark.slow
def test_score_comments_real_model_gets_sign_right():
    scores = score_comments(["this is amazing content", "worst video ever, total slop"])
    assert scores[0] > 0
    assert scores[1] < 0
