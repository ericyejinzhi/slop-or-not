"""Tests sloppy.ingest.pipeline.ingest_channel - specifically the `limit` parameter
added after discovering, while bulk-ingesting real seed channels, that several
real-world channels (PewDiePie, Markiplier, jacksepticeye) have thousands of videos and
ingest_channel previously had no way to cap that. Real network calls are monkeypatched,
following the same pattern as test_ingest_pipeline_single_video.py - this is the first
test coverage ingest_channel itself has ever had.
"""

from datetime import UTC, datetime

import pytest

from sloppy.config import Settings
from sloppy.db.models import Channel, Video
from sloppy.db.session import session_scope
from sloppy.ingest import pipeline
from sloppy.ingest.youtube import ChannelMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_ingest_channel_limit"
TEST_VIDEO_PREFIX = "test_ingest_channel_limit_video_"

_TEST_SETTINGS = Settings(_env_file=None)


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Video).filter(Video.channel_id == TEST_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _fake_video_meta(video_id: str) -> VideoMeta:
    return VideoMeta(
        id=video_id,
        channel_id=TEST_CHANNEL_ID,
        title=f"Title for {video_id}",
        published_at=datetime.now(UTC),
    )


def _patch_network(monkeypatch, *, total_available: int | None):
    """total_available=None means an effectively infinite uploads playlist - if
    ingest_channel ever fully drains this instead of using itertools.islice to stop
    early, a limited-ingest test using it would hang forever, immediately catching a
    regression rather than silently passing.
    """
    monkeypatch.setattr(pipeline, "get_youtube_client", lambda settings: object())
    monkeypatch.setattr(pipeline, "get_s3_client", lambda settings: object())
    monkeypatch.setattr(pipeline, "ensure_bucket", lambda client, bucket: None)
    monkeypatch.setattr(
        pipeline,
        "resolve_channel",
        lambda client, id_: ChannelMeta(
            id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"
        ),
    )

    def fake_iter_playlist_video_ids(client, playlist_id):
        i = 0
        while total_available is None or i < total_available:
            yield f"{TEST_VIDEO_PREFIX}{i}"
            i += 1

    monkeypatch.setattr(pipeline, "iter_playlist_video_ids", fake_iter_playlist_video_ids)
    monkeypatch.setattr(
        pipeline,
        "fetch_videos_metadata",
        lambda client, ids: [_fake_video_meta(video_id) for video_id in ids],
    )
    monkeypatch.setattr(pipeline, "fetch_top_comments", lambda client, video_id, limit: [])
    monkeypatch.setattr(
        pipeline, "extract_thumbnail_url", lambda video_id: (_ for _ in ()).throw(RuntimeError())
    )


def test_ingest_channel_with_limit_stops_early_on_an_effectively_infinite_playlist(
    monkeypatch,
):
    """The real regression this guards against: if `limit` were implemented by fully
    materializing iter_playlist_video_ids into a list before truncating, this test would
    hang forever against an infinite generator instead of completing quickly."""
    _cleanup()
    try:
        _patch_network(monkeypatch, total_available=None)

        summary = pipeline.ingest_channel(_TEST_SETTINGS, "@fake", limit=5)

        assert summary.videos_upserted == 5
        with session_scope() as session:
            count = session.query(Video).filter(Video.channel_id == TEST_CHANNEL_ID).count()
            assert count == 5
    finally:
        _cleanup()


def test_ingest_channel_without_limit_ingests_everything_available(monkeypatch):
    _cleanup()
    try:
        _patch_network(monkeypatch, total_available=8)

        summary = pipeline.ingest_channel(_TEST_SETTINGS, "@fake", limit=None)

        assert summary.videos_upserted == 8
    finally:
        _cleanup()


def test_ingest_channel_limit_larger_than_available_ingests_all_available(monkeypatch):
    _cleanup()
    try:
        _patch_network(monkeypatch, total_available=3)

        summary = pipeline.ingest_channel(_TEST_SETTINGS, "@fake", limit=100)

        assert summary.videos_upserted == 3
    finally:
        _cleanup()


def test_ingest_channel_sampling_stops_early_and_stays_within_the_window(monkeypatch):
    """Guards the same regression `limit` already guards against (full-materialization
    before truncating would hang on an infinite playlist), plus the sampling-specific
    property that every chosen id actually came from within `sample_window`, not just
    anywhere in the (effectively infinite) playlist."""
    _cleanup()
    try:
        _patch_network(monkeypatch, total_available=None)

        summary = pipeline.ingest_channel(_TEST_SETTINGS, "@fake", sample_window=20, sample_size=5)

        assert summary.videos_upserted == 5
        with session_scope() as session:
            video_ids = [
                row.id for row in session.query(Video).filter(Video.channel_id == TEST_CHANNEL_ID)
            ]
        assert len(video_ids) == 5
        indices = {int(vid.removeprefix(TEST_VIDEO_PREFIX)) for vid in video_ids}
        assert indices.issubset(set(range(20)))
    finally:
        _cleanup()


def test_ingest_channel_sampling_returns_fewer_if_window_has_fewer_than_sample_size(
    monkeypatch,
):
    _cleanup()
    try:
        _patch_network(monkeypatch, total_available=3)

        summary = pipeline.ingest_channel(_TEST_SETTINGS, "@fake", sample_window=20, sample_size=10)

        assert summary.videos_upserted == 3
    finally:
        _cleanup()


def test_ingest_channel_sampling_requires_both_window_and_size_together():
    with pytest.raises(ValueError, match="sample_window and sample_size"):
        pipeline.ingest_channel(_TEST_SETTINGS, "@fake", sample_window=20)

    with pytest.raises(ValueError, match="sample_window and sample_size"):
        pipeline.ingest_channel(_TEST_SETTINGS, "@fake", sample_size=10)
