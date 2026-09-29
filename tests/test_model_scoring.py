"""Tests sloppy.models.scoring.score_videos - the "score already-ingested unlabeled
videos with an existing model" capability Phase 7's flow needs, which nothing before it
could do (assemble_dataset requires a splits.csv label; training always fit a fresh
model, never reloaded a saved one to score new data with).
"""

from datetime import UTC, datetime

import pandas as pd

from sloppy.db.models import Channel, Video, VideoScore
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.models.scoring import score_videos
from sloppy.models.train import (
    METADATA_CATEGORICAL_FEATURES,
    METADATA_NUMERIC_FEATURES,
    save_model,
    train_model,
)

TEST_CHANNEL_ID = "UC_test_scoring_channel"
TEST_VIDEO_ID = "test_scoring_video_0001"
# save_model persists under trained.name (the name passed to train_model), so this must
# match that, not an arbitrary label - artifacts_dir/logistic_regression/test-version/.
TEST_MODEL_NAME = "logistic_regression"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(VideoScore).filter(VideoScore.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _training_dataframe(n: int = 20) -> pd.DataFrame:
    """A tiny synthetic metadata-only training set - score_videos only needs SOME
    trained pipeline to load back and apply, not a statistically meaningful one."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "title_caps_ratio": 0.1,
                "title_emoji_count": 0,
                "title_clickbait_score": 0.0,
                "description_length": 100,
                "tag_count": 3,
                "like_view_ratio": 0.05,
                "comment_view_ratio": 0.01,
                "duration_seconds": 600,
                "duration_deviation_channel": 3.0 if i % 2 == 0 else -3.0,
                "duration_deviation_genre": 0.0,
                "channel_upload_cadence_days": 7.0,
                "title_curiosity_gap_count": 0,
                "title_unresolved_pronoun_count": 0,
                "title_all_caps_span_count": 0,
                "title_ellipsis_count": 0,
                "duration_bucket": "mid",
                "genre": "Gaming",
                "y": 1 if i % 2 == 0 else 0,
            }
        )
    return pd.DataFrame(rows)


def test_score_videos_scores_and_upserts(tmp_path):
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
                    title="Some Title",
                    published_at=datetime.now(UTC),
                    duration_seconds=600,
                    view_count=1000,
                    like_count=50,
                    comment_count=5,
                ),
            )

        train_df = _training_dataframe()
        trained = train_model(
            "logistic_regression",
            train_df,
            numeric_features=METADATA_NUMERIC_FEATURES,
            categorical_features=METADATA_CATEGORICAL_FEATURES,
            version="test-version",
        )
        save_model(trained, tmp_path, train_row_count=len(train_df))

        scored_ids = score_videos(
            video_ids=[TEST_VIDEO_ID],
            model_name=TEST_MODEL_NAME,
            model_version="test-version",
            artifacts_dir=tmp_path,
        )

        assert scored_ids == [TEST_VIDEO_ID]
        with session_scope() as session:
            row = (
                session.query(VideoScore)
                .filter(
                    VideoScore.video_id == TEST_VIDEO_ID,
                    VideoScore.model_name == TEST_MODEL_NAME,
                    VideoScore.model_version == "test-version",
                )
                .one()
            )
            assert row.split == "live"
            assert row.predicted_label in ("up", "down")
            assert 0.0 <= row.score <= 1.0
    finally:
        _cleanup()


def test_score_videos_skips_nonexistent_video_ids(tmp_path):
    _cleanup()
    try:
        train_df = _training_dataframe()
        trained = train_model(
            "logistic_regression",
            train_df,
            numeric_features=METADATA_NUMERIC_FEATURES,
            categorical_features=METADATA_CATEGORICAL_FEATURES,
            version="test-version",
        )
        save_model(trained, tmp_path, train_row_count=len(train_df))

        scored_ids = score_videos(
            video_ids=["does-not-exist"],
            model_name=TEST_MODEL_NAME,
            model_version="test-version",
            artifacts_dir=tmp_path,
        )

        assert scored_ids == []
    finally:
        _cleanup()
