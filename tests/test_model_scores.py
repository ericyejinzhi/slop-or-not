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


def test_upsert_video_score_preserve_split_keeps_the_trained_split_but_updates_the_score():
    # Regression: scoring an already-trained-on video with the active model used to
    # overwrite its recorded "train"/"val"/"test" split with "live", corrupting the
    # split-based evaluation (`slop model evaluate` reads VideoScore.split).
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

        def upsert(score, split, preserve_split):
            with session_scope() as session:
                upsert_video_score(
                    session,
                    video_id=TEST_VIDEO_ID,
                    model_name="logistic_regression",
                    model_version="v_preserve",
                    score=score,
                    predicted_label="down" if score >= 0.5 else "up",
                    split=split,
                    preserve_split=preserve_split,
                )

        def current():
            with session_scope() as session:
                row = session.query(VideoScore).filter(VideoScore.video_id == TEST_VIDEO_ID).one()
                return row.score, row.split

        upsert(0.3, "train", preserve_split=False)  # as written by `slop model train`
        upsert(0.9, "live", preserve_split=True)  # as written by live scoring
        assert current() == (0.9, "train")

        upsert(0.1, "live", preserve_split=False)  # the default still overwrites
        assert current() == (0.1, "live")

        # a brand-new row gets the split it is given even with preserve_split=True
        with session_scope() as session:
            session.query(VideoScore).filter(VideoScore.video_id == TEST_VIDEO_ID).delete()
        upsert(0.6, "live", preserve_split=True)
        assert current() == (0.6, "live")
    finally:
        _cleanup()
