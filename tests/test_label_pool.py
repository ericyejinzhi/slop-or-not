from datetime import UTC, datetime, timedelta

from sloppy.db.models import Channel, Label, Video
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.label.labels import record_label
from sloppy.label.pool import PoolVideo, candidate_videos, consistency_sample, sample_pool

TEST_CHANNEL_ID = "UC_test_pool_channel"
TEST_VIDEO_PREFIX = "test_pool_video_"


def _pool_video(video_id: str) -> PoolVideo:
    return PoolVideo(
        video_id=video_id,
        channel_id="chan",
        channel_handle="@chan",
        published_at=datetime.now(UTC),
    )


def test_sample_pool_truncates_to_target_size():
    candidates = [_pool_video(f"v{i}") for i in range(10)]
    sampled = sample_pool(candidates, target_size=3, seed=1)
    assert len(sampled) == 3
    assert len({v.video_id for v in sampled}) == 3


def test_sample_pool_returns_all_when_fewer_than_target():
    candidates = [_pool_video(f"v{i}") for i in range(3)]
    sampled = sample_pool(candidates, target_size=10, seed=1)
    assert len(sampled) == 3


def test_sample_pool_is_deterministic_given_seed():
    candidates = [_pool_video(f"v{i}") for i in range(20)]
    first = [v.video_id for v in sample_pool(candidates, target_size=5, seed=42)]
    second = [v.video_id for v in sample_pool(candidates, target_size=5, seed=42)]
    assert first == second


def _cleanup() -> None:
    with session_scope() as session:
        video_ids = [
            row[0] for row in session.query(Video.id).filter(Video.channel_id == TEST_CHANNEL_ID)
        ]
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Video).filter(Video.channel_id == TEST_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def test_candidate_videos_caps_per_channel_and_picks_most_recent():
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )
            now = datetime.now(UTC)
            for i in range(5):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{TEST_VIDEO_PREFIX}{i}",
                        channel_id=TEST_CHANNEL_ID,
                        title=f"Video {i}",
                        published_at=now - timedelta(days=i),
                    ),
                )

        with session_scope() as session:
            candidates = candidate_videos(session, per_channel_max=2, exclude_labeled=False)

        this_channel = [c for c in candidates if c.channel_id == TEST_CHANNEL_ID]
        assert len(this_channel) == 2
        assert {c.video_id for c in this_channel} == {
            f"{TEST_VIDEO_PREFIX}0",
            f"{TEST_VIDEO_PREFIX}1",
        }
    finally:
        _cleanup()


def test_consistency_sample_only_returns_non_skip_labeled_videos():
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )
            now = datetime.now(UTC)
            for i in range(3):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{TEST_VIDEO_PREFIX}{i}",
                        channel_id=TEST_CHANNEL_ID,
                        title=f"Video {i}",
                        published_at=now,
                    ),
                )

        with session_scope() as session:
            record_label(session, video_id=f"{TEST_VIDEO_PREFIX}0", labeler="t", label="up")
            record_label(session, video_id=f"{TEST_VIDEO_PREFIX}1", labeler="t", label="skip")
            # video 2 has no label at all

        with session_scope() as session:
            sampled = consistency_sample(session, n=10)

        this_channel_ids = {v.video_id for v in sampled if v.channel_id == TEST_CHANNEL_ID}
        assert this_channel_ids == {f"{TEST_VIDEO_PREFIX}0"}
    finally:
        _cleanup()
