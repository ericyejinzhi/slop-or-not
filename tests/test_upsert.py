"""Integration tests against the real dev Postgres (docker compose up -d) proving upserts
are idempotent — the exact mechanism Stage 5's `slop ingest channel` re-run safety relies on.
"""

from datetime import UTC, datetime

from sloppy.db.models import Channel, Comment, Thumbnail, Video
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_comment, upsert_thumbnail, upsert_video
from sloppy.ingest.youtube import ChannelMeta, CommentMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_upsert_channel"
TEST_VIDEO_ID = "test_upsert_video_0001"
TEST_COMMENT_ID = "test_upsert_comment_001"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Comment).filter(Comment.video_id == TEST_VIDEO_ID).delete()
        session.query(Thumbnail).filter(Thumbnail.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def test_upsert_channel_updates_in_place_without_duplicating():
    _cleanup()
    try:
        channel = ChannelMeta(
            id=TEST_CHANNEL_ID,
            handle="@test",
            title="Test Channel",
            uploads_playlist_id="UU_test",
        )
        with session_scope() as session:
            upsert_channel(session, channel)
        with session_scope() as session:
            first_created_at = session.get(Channel, TEST_CHANNEL_ID).created_at

        channel.title = "Test Channel (updated)"
        with session_scope() as session:
            upsert_channel(session, channel)

        with session_scope() as session:
            rows = session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).all()
            assert len(rows) == 1
            assert rows[0].title == "Test Channel (updated)"
            assert rows[0].created_at == first_created_at
            assert rows[0].updated_at >= first_created_at
    finally:
        _cleanup()


def test_upsert_video_comment_thumbnail_reruns_without_duplicating():
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(
                    id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_test"
                ),
            )

        video = VideoMeta(
            id=TEST_VIDEO_ID,
            channel_id=TEST_CHANNEL_ID,
            title="Test Video",
            published_at=datetime.now(UTC),
        )
        comment = CommentMeta(
            id=TEST_COMMENT_ID, video_id=TEST_VIDEO_ID, text="hello", published_at=datetime.now(UTC)
        )
        thumbnail_kwargs = {
            "video_id": TEST_VIDEO_ID,
            "s3_bucket": "thumbnails",
            "s3_key": f"{TEST_VIDEO_ID}.jpg",
            "content_type": "image/jpeg",
            "width": 100,
            "height": 100,
            "source_url": "https://example.com/thumb.jpg",
            "downloaded_at": datetime.now(UTC),
        }

        for _ in range(2):  # run twice — the second run must not create duplicates
            with session_scope() as session:
                upsert_video(session, video)
                upsert_comment(session, comment)
                upsert_thumbnail(session, **thumbnail_kwargs)

        with session_scope() as session:
            assert session.query(Video).filter(Video.id == TEST_VIDEO_ID).count() == 1
            assert session.query(Comment).filter(Comment.id == TEST_COMMENT_ID).count() == 1
            assert session.query(Thumbnail).filter(Thumbnail.video_id == TEST_VIDEO_ID).count() == 1
    finally:
        _cleanup()
