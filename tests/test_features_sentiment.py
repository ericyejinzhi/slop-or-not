import pytest

from sloppy.features import sentiment
from sloppy.features.sentiment import (
    _token_budget_batches,
    aggregate_sentiment,
    channel_sentiment_rollup,
    score_comments,
)


class _FakeTokenizer:
    """One 'token' per whitespace-separated word, truncated like the real one."""

    def __call__(self, texts, truncation, max_length):
        return {"input_ids": [t.split()[:max_length] for t in texts]}


class _FakePipeline:
    """Stands in for the HuggingFace pipeline: records each call and answers with a
    positive probability encoding the text's own word count (so ordering mistakes show)."""

    def __init__(self):
        self.tokenizer = _FakeTokenizer()
        self.calls = []

    def __call__(self, texts, **kwargs):
        self.calls.append({"texts": list(texts), **kwargs})
        return [
            [
                {"label": "positive", "score": len(t.split()) / 100},
                {"label": "negative", "score": 0.0},
                {"label": "neutral", "score": 1 - len(t.split()) / 100},
            ]
            for t in texts
        ]


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


def test_score_comments_always_truncates(monkeypatch):
    # Regression: a comment past the model's 512-token limit crashed real ingestion data
    # ("index 514 is out of bounds") because the pipeline was called without truncation.
    fake = _FakePipeline()
    monkeypatch.setattr(sentiment, "_load_pipeline", lambda: fake)

    scores = score_comments(["word " * 2000])

    assert len(fake.calls) == 1
    assert fake.calls[0]["truncation"] is True
    assert fake.calls[0]["max_length"] == 512
    assert len(scores) == 1


def test_score_comments_returns_scores_in_the_original_order_despite_length_sorting(monkeypatch):
    # The pipeline sees texts sorted by length; scores must still line up with the input.
    fake = _FakePipeline()
    monkeypatch.setattr(sentiment, "_load_pipeline", lambda: fake)
    inputs = ["w " * 30, "w " * 5, "w " * 50, "w " * 12]

    scores = score_comments(inputs)

    seen = [t for call in fake.calls for t in call["texts"]]
    assert [len(t.split()) for t in seen] == [5, 12, 30, 50]  # shortest first
    assert scores == pytest.approx([0.30, 0.05, 0.50, 0.12])


def test_score_comments_batches_by_padded_token_budget_not_a_fixed_count(monkeypatch):
    # 40 one-word comments fit in one pass; a 600-word comment (truncated to 512 tokens,
    # over the budget by itself) must get its own pass instead of padding the others.
    fake = _FakePipeline()
    monkeypatch.setattr(sentiment, "_load_pipeline", lambda: fake)
    inputs = ["hi"] * 40 + ["word " * 600]

    scores = score_comments(inputs)

    sizes = [len(call["texts"]) for call in fake.calls]
    assert sizes == [40, 1]
    assert [call["batch_size"] for call in fake.calls] == [40, 1]  # one forward pass each
    assert scores[:3] == pytest.approx([0.01] * 3)


def test_token_budget_batches_respects_the_token_budget_and_the_size_cap():
    # lengths ascending; a batch's padded size is count x its longest length
    assert _token_budget_batches([10] * 10) == [(0, 10)]
    assert _token_budget_batches([300, 300, 300, 300]) == [(0, 3), (3, 4)]  # 3 x 300 <= 1024
    assert _token_budget_batches([1] * 130) == [(0, 64), (64, 128), (128, 130)]  # size cap
    assert _token_budget_batches([512]) == [(0, 1)]
    assert _token_budget_batches([512, 512]) == [(0, 2)]  # 2 x 512 = exactly the budget
    assert _token_budget_batches([512, 512, 512]) == [(0, 2), (2, 3)]


def test_token_budget_batches_cover_every_index_exactly_once():
    lengths = sorted([3, 3, 4, 8, 20, 21, 90, 250, 512, 512])
    covered = [i for start, stop in _token_budget_batches(lengths) for i in range(start, stop)]
    assert covered == list(range(len(lengths)))


@pytest.mark.slow
def test_score_comments_real_model_gets_sign_right():
    scores = score_comments(["this is amazing content", "worst video ever, total slop"])
    assert scores[0] > 0
    assert scores[1] < 0
