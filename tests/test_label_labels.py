from datetime import UTC, datetime

from sloppy.db.models import Channel, Label, Video
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.label.labels import record_label

TEST_CHANNEL_ID = "UC_test_label_channel"
TEST_VIDEO_ID = "test_label_video_0001"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Label).filter(Label.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def test_record_label_allows_multiple_rows_per_video():
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )
            upsert_video(
                session,
                VideoMeta(
                    id=TEST_VIDEO_ID,
                    channel_id=TEST_CHANNEL_ID,
                    title="Test Video",
                    published_at=datetime.now(UTC),
                ),
            )

        with session_scope() as session:
            record_label(session, video_id=TEST_VIDEO_ID, labeler="alice", label="up")
        with session_scope() as session:
            record_label(
                session,
                video_id=TEST_VIDEO_ID,
                labeler="alice",
                label="down",
                notes="changed my mind",
            )

        with session_scope() as session:
            rows = (
                session.query(Label)
                .filter(Label.video_id == TEST_VIDEO_ID)
                .order_by(Label.id)
                .all()
            )
            assert [r.label for r in rows] == ["up", "down"]
            assert rows[1].notes == "changed my mind"
    finally:
        _cleanup()
