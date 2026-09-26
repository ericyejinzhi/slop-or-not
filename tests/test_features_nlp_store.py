"""Integration test against real Postgres proving video_nlp_features upserts overwrite
in place on video_id alone (unlike video_scores' composite key) - mirrors
tests/test_model_scores.py's pattern.
"""

from datetime import UTC, datetime

from sloppy.db.models import Channel, Video, VideoNlpFeatures
from sloppy.db.session import session_scope
from sloppy.features.nlp_store import upsert_video_nlp_features
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_nlp_store_channel"
TEST_VIDEO_ID = "test_nlp_store_video_0001"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(VideoNlpFeatures).filter(VideoNlpFeatures.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _base_fields(**overrides) -> dict:
    fields = {
        "comment_count_scored": 10,
        "sentiment_mean": 0.2,
        "sentiment_std": 0.5,
        "sentiment_negative_share": 0.3,
        "slop_keyword_rate": 0.0,
        "topic_cluster_count": 3,
        "topic_top_cluster_share": 0.4,
        "topic_top_cluster_sentiment": 0.1,
        "topic_sentiment_spread": 0.2,
        "title_lure_score": 0.1,
        "title_mysterious_score": 0.2,
        "title_transparent_score": 0.3,
        "title_embedding": [0.1] * 384,
        "description_embedding": [0.2] * 384,
        "comment_embedding_mean": [0.3] * 384,
        "sentiment_model": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    }
    fields.update(overrides)
    return fields


def test_upsert_video_nlp_features_updates_in_place():
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
            upsert_video_nlp_features(session, video_id=TEST_VIDEO_ID, **_base_fields())
        with session_scope() as session:
            upsert_video_nlp_features(
                session, video_id=TEST_VIDEO_ID, **_base_fields(sentiment_mean=0.9)
            )

        with session_scope() as session:
            rows = (
                session.query(VideoNlpFeatures)
                .filter(VideoNlpFeatures.video_id == TEST_VIDEO_ID)
                .all()
            )
            assert len(rows) == 1
            assert rows[0].sentiment_mean == 0.9
    finally:
        _cleanup()


def test_upsert_video_nlp_features_stores_embedding_dimensions():
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
            upsert_video_nlp_features(session, video_id=TEST_VIDEO_ID, **_base_fields())

        with session_scope() as session:
            row = session.get(VideoNlpFeatures, TEST_VIDEO_ID)
            assert len(row.title_embedding) == 384
            assert len(row.description_embedding) == 384
            assert len(row.comment_embedding_mean) == 384
    finally:
        _cleanup()
