"""Integration test against real Postgres proving video_score upserts are idempotent per
(video_id, model_name, model_version) - mirrors tests/test_upsert.py's pattern.
"""

from datetime import UTC, datetime

from sloppy.db.models import Channel, Video, VideoScore
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.models.scores import upsert_video_score

TEST_CHANNEL_ID = "UC_test_scores_channel"
TEST_VIDEO_ID = "test_scores_video_0001"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(VideoScore).filter(VideoScore.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def test_upsert_video_score_updates_in_place_for_same_model_version():
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
            upsert_video_score(
                session,
                video_id=TEST_VIDEO_ID,
                model_name="logistic_regression",
                model_version="v1",
                score=0.3,
                predicted_label="up",
                split="test",
            )
        with session_scope() as session:
            upsert_video_score(
                session,
                video_id=TEST_VIDEO_ID,
                model_name="logistic_regression",
                model_version="v1",
                score=0.8,
                predicted_label="down",
                split="test",
            )

        with session_scope() as session:
            rows = session.query(VideoScore).filter(VideoScore.video_id == TEST_VIDEO_ID).all()
            assert len(rows) == 1
            assert rows[0].score == 0.8
            assert rows[0].predicted_label == "down"
    finally:
        _cleanup()


def test_upsert_video_score_keeps_different_model_versions_side_by_side():
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
            upsert_video_score(
                session,
                video_id=TEST_VIDEO_ID,
                model_name="logistic_regression",
                model_version="v1",
                score=0.3,
                predicted_label="up",
                split="test",
            )
            upsert_video_score(
                session,
                video_id=TEST_VIDEO_ID,
                model_name="xgboost",
                model_version="v1",
                score=0.7,
                predicted_label="down",
                split="test",
            )

        with session_scope() as session:
            rows = session.query(VideoScore).filter(VideoScore.video_id == TEST_VIDEO_ID).all()
            assert {(r.model_name, r.score) for r in rows} == {
                ("logistic_regression", 0.3),
                ("xgboost", 0.7),
            }
    finally:
        _cleanup()
