"""Tests sloppy.ingest.pipeline.ingest_video. Fully offline: the YouTube client,
fetch_videos_metadata/fetch_top_comments/resolve_channel, the S3 client, and thumbnail
extraction are all monkeypatched, so this never touches the real YouTube API or network.
extract_thumbnail_url is monkeypatched to raise, which exercises _ingest_video's existing
try/except around thumbnail extraction (video/comments still upsert, thumbnail is just
skipped) rather than needing to fake yt-dlp/urllib.

Integration test against the real dev Postgres (docker compose up -d) for the DB side -
fixture rows/cleanup follow the project's standard pattern.
"""

from datetime import UTC, datetime

import pytest

from sloppy.config import Settings
from sloppy.db.models import Channel, Video
from sloppy.db.session import session_scope
from sloppy.ingest import pipeline
from sloppy.ingest.upsert import upsert_channel
from sloppy.ingest.youtube import ChannelMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_single_video_channel"
TEST_VIDEO_ID = "test_single_video_0001"

_TEST_SETTINGS = Settings(_env_file=None)


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _fake_video_meta() -> VideoMeta:
    return VideoMeta(
        id=TEST_VIDEO_ID,
        channel_id=TEST_CHANNEL_ID,
        title="Test Video",
        published_at=datetime.now(UTC),
    )


def _raise_no_thumbnail(video_id: str):
    raise RuntimeError("no thumbnail in test")


def _patch_network(monkeypatch):
    monkeypatch.setattr(pipeline, "get_youtube_client", lambda settings: object())
    monkeypatch.setattr(pipeline, "get_s3_client", lambda settings: object())
    monkeypatch.setattr(pipeline, "ensure_bucket", lambda client, bucket: None)
    monkeypatch.setattr(pipeline, "fetch_videos_metadata", lambda client, ids: [_fake_video_meta()])
    monkeypatch.setattr(pipeline, "fetch_top_comments", lambda client, video_id, limit: [])
    monkeypatch.setattr(pipeline, "extract_thumbnail_url", _raise_no_thumbnail)


def test_ingest_video_skips_resolve_channel_when_channel_already_exists(monkeypatch):
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )

        _patch_network(monkeypatch)
        resolve_calls = []
        monkeypatch.setattr(
            pipeline,
            "resolve_channel",
            lambda client, id_: resolve_calls.append(id_),
        )

        summary = pipeline.ingest_video(_TEST_SETTINGS, TEST_VIDEO_ID)

        assert summary.videos_upserted == 1
        assert summary.channel_id == TEST_CHANNEL_ID
        assert resolve_calls == []

        with session_scope() as session:
            assert session.get(Video, TEST_VIDEO_ID) is not None
    finally:
        _cleanup()


def test_ingest_video_resolves_and_upserts_a_novel_channel(monkeypatch):
    _cleanup()
    try:
        _patch_network(monkeypatch)
        monkeypatch.setattr(
            pipeline,
            "resolve_channel",
            lambda client, id_: ChannelMeta(
                id=TEST_CHANNEL_ID, title="Novel Channel", uploads_playlist_id="UU_x"
            ),
        )

        summary = pipeline.ingest_video(_TEST_SETTINGS, TEST_VIDEO_ID)

        assert summary.videos_upserted == 1
        with session_scope() as session:
            assert session.get(Channel, TEST_CHANNEL_ID) is not None
            assert session.get(Video, TEST_VIDEO_ID) is not None
    finally:
        _cleanup()


def test_ingest_video_raises_value_error_when_video_not_found(monkeypatch):
    monkeypatch.setattr(pipeline, "get_youtube_client", lambda settings: object())
    monkeypatch.setattr(pipeline, "get_s3_client", lambda settings: object())
    monkeypatch.setattr(pipeline, "ensure_bucket", lambda client, bucket: None)
    monkeypatch.setattr(pipeline, "fetch_videos_metadata", lambda client, ids: [])

    with pytest.raises(ValueError):
        pipeline.ingest_video(_TEST_SETTINGS, "nonexistent")
