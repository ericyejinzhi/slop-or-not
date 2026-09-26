from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sloppy.features.corpus import build_corpus_stats, primary_genre, upload_cadence_days


def test_primary_genre_extracts_last_path_segment():
    assert primary_genre(["https://en.wikipedia.org/wiki/Gaming"]) == "Gaming"


def test_primary_genre_unknown_for_empty():
    assert primary_genre(None) == "unknown"
    assert primary_genre([]) == "unknown"


def test_upload_cadence_days_median_gap():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    dates = [base, base + timedelta(days=2), base + timedelta(days=4), base + timedelta(days=10)]
    # gaps: 2, 2, 6 -> median 2
    assert upload_cadence_days(dates) == 2.0


def test_upload_cadence_days_none_with_fewer_than_two():
    assert upload_cadence_days([datetime(2026, 1, 1, tzinfo=UTC)]) is None
    assert upload_cadence_days([]) is None


@dataclass
class FakeVideo:
    id: str
    channel_id: str
    duration_seconds: int | None
    published_at: datetime
    topic_categories: list[str] | None


def _fake_corpus() -> list[FakeVideo]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    videos = []
    # channel "c1", genre Gaming: 5 videos, durations 500-700s
    for i in range(5):
        videos.append(
            FakeVideo(
                id=f"c1_v{i}",
                channel_id="c1",
                duration_seconds=500 + i * 50,
                published_at=base + timedelta(days=i * 3),
                topic_categories=["https://en.wikipedia.org/wiki/Gaming"],
            )
        )
    # channel "c2", genre Cooking: 5 videos, durations 200-400s
    for i in range(5):
        videos.append(
            FakeVideo(
                id=f"c2_v{i}",
                channel_id="c2",
                duration_seconds=200 + i * 50,
                published_at=base + timedelta(days=i * 7),
                topic_categories=["https://en.wikipedia.org/wiki/Cooking"],
            )
        )
    # channel "c3", genre Gaming: 5 videos, no duration (still ingesting / livestream)
    for i in range(5):
        videos.append(
            FakeVideo(
                id=f"c3_v{i}",
                channel_id="c3",
                duration_seconds=None,
                published_at=base + timedelta(days=i),
                topic_categories=["https://en.wikipedia.org/wiki/Gaming"],
            )
        )
    return videos


def test_build_corpus_stats_groups_durations_by_channel():
    stats = build_corpus_stats(_fake_corpus())
    assert stats.durations_by_channel["c1"] == [500, 550, 600, 650, 700]
    assert stats.durations_by_channel["c2"] == [200, 250, 300, 350, 400]
    # c3 has no durations at all - should not contribute an empty list either way,
    # but definitely should not appear with non-None values
    assert "c3" not in stats.durations_by_channel or stats.durations_by_channel["c3"] == []


def test_build_corpus_stats_groups_durations_by_genre_across_channels():
    stats = build_corpus_stats(_fake_corpus())
    # Gaming genre pools c1's durations only (c3 has no durations to contribute)
    assert sorted(stats.durations_by_genre["Gaming"]) == [500, 550, 600, 650, 700]
    assert sorted(stats.durations_by_genre["Cooking"]) == [200, 250, 300, 350, 400]


def test_build_corpus_stats_tracks_published_dates_per_channel():
    stats = build_corpus_stats(_fake_corpus())
    assert len(stats.published_dates_by_channel["c1"]) == 5
    assert len(stats.published_dates_by_channel["c3"]) == 5
