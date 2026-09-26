from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sloppy.features.corpus import CorpusStats, build_corpus_stats
from sloppy.features.extract import extract_features


@dataclass
class FakeVideo:
    id: str
    channel_id: str
    duration_seconds: int | None
    published_at: datetime
    topic_categories: list[str] | None
    title: str
    description: str | None
    tags: list[str] | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None


def test_extract_features_produces_expected_record():
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # A small fake corpus: the target video's channel has 3 videos (500, 600, 700s), so
    # the target's own duration (600) is dead-center - deviation should be ~0.
    channel_videos = [
        FakeVideo(
            id=f"c1_v{i}",
            channel_id="c1",
            duration_seconds=d,
            published_at=base + timedelta(days=i * 5),
            topic_categories=["https://en.wikipedia.org/wiki/Gaming"],
            title=f"Video {i}",
            description=None,
            tags=None,
            view_count=None,
            like_count=None,
            comment_count=None,
        )
        for i, d in enumerate([500, 600, 700])
    ]

    target = FakeVideo(
        id="c1_v1",
        channel_id="c1",
        duration_seconds=600,
        published_at=base + timedelta(days=5),
        topic_categories=["https://en.wikipedia.org/wiki/Gaming"],
        title="YOU WON'T BELIEVE THIS!!!",
        description="a short description",
        tags=["tag1", "tag2"],
        view_count=1000,
        like_count=100,
        comment_count=20,
    )

    corpus: CorpusStats = build_corpus_stats(channel_videos)
    features = extract_features(target, corpus)

    assert features.video_id == "c1_v1"
    assert features.channel_id == "c1"
    assert features.title_caps_ratio == 1.0  # "YOUWONTBELIEVETHIS" - all caps
    assert features.title_clickbait_score > 0  # matches "you won't believe" and "!!!"
    assert features.description_length == len("a short description")
    assert features.tag_count == 2
    assert features.like_view_ratio == 0.1  # 100/1000
    assert features.comment_view_ratio == 0.02  # 20/1000
    assert features.duration_seconds == 600
    assert features.duration_bucket == "mid"
    assert features.duration_deviation_channel is not None
    assert abs(features.duration_deviation_channel) < 0.5  # dead-center among peers
    assert features.duration_deviation_genre is not None
    assert features.channel_upload_cadence_days == 5.0  # every 5 days in this fake corpus
    assert features.genre == "Gaming"
    assert features.title_curiosity_gap_count == 0
    assert features.title_unresolved_pronoun_count == 1  # "this"
    assert features.title_all_caps_span_count == 4  # YOU, WON, BELIEVE, THIS
    assert features.title_ellipsis_count == 0


def test_extract_features_handles_missing_view_count_and_duration():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    target = FakeVideo(
        id="v1",
        channel_id="c1",
        duration_seconds=None,
        published_at=base,
        topic_categories=None,
        title="plain title",
        description=None,
        tags=None,
        view_count=None,
        like_count=None,
        comment_count=None,
    )
    corpus = build_corpus_stats([target])
    features = extract_features(target, corpus)

    assert features.like_view_ratio is None
    assert features.comment_view_ratio is None
    assert features.duration_bucket == "unknown"
    assert features.duration_deviation_channel is None
    assert features.duration_deviation_genre is None
    assert features.genre == "unknown"
