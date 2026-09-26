"""Integration test against real Postgres, proving the pgvector <=> cosine-distance
queries produce correct results - data is fully synthetic/hand-picked (known vectors),
so expected values are exact. "Nearest neighbors look right" on REAL data is explicitly
deferred, same category as Phase 3's baseline-lift check.
"""

from datetime import UTC, datetime

from sloppy.db.models import Channel, Video, VideoNlpFeatures, VideoVisionFeatures
from sloppy.db.session import session_scope
from sloppy.features.nlp_store import upsert_video_nlp_features
from sloppy.features.similarity import (
    channel_thumbnail_self_similarity_mean,
    channel_title_self_similarity_mean,
    near_duplicate_thumbnail_count,
)
from sloppy.features.vision_store import upsert_video_vision_features
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_similarity_channel"
VIDEO_IDS = ["test_similarity_v1", "test_similarity_v2", "test_similarity_v3"]


def _unit_vector(dim: int, axis: int) -> list[float]:
    vec = [0.0] * dim
    vec[axis] = 1.0
    return vec


def _cleanup() -> None:
    with session_scope() as session:
        session.query(VideoVisionFeatures).filter(
            VideoVisionFeatures.video_id.in_(VIDEO_IDS)
        ).delete(synchronize_session=False)
        session.query(VideoNlpFeatures).filter(VideoNlpFeatures.video_id.in_(VIDEO_IDS)).delete(
            synchronize_session=False
        )
        session.query(Video).filter(Video.id.in_(VIDEO_IDS)).delete(synchronize_session=False)
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _nlp_fields(title_embedding: list[float]) -> dict:
    return {
        "comment_count_scored": 0,
        "sentiment_mean": None,
        "sentiment_std": None,
        "sentiment_negative_share": None,
        "slop_keyword_rate": None,
        "topic_cluster_count": None,
        "topic_top_cluster_share": None,
        "topic_top_cluster_sentiment": None,
        "topic_sentiment_spread": None,
        "title_lure_score": 0.0,
        "title_mysterious_score": 0.0,
        "title_transparent_score": 0.0,
        "title_embedding": title_embedding,
        "description_embedding": None,
        "comment_embedding_mean": None,
        "sentiment_model": "test",
        "embedding_model": "test",
    }


def test_similarity_functions_against_known_vectors():
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )
            for video_id in VIDEO_IDS:
                upsert_video(
                    session,
                    VideoMeta(
                        id=video_id,
                        channel_id=TEST_CHANNEL_ID,
                        title="Test Video",
                        published_at=datetime.now(UTC),
                    ),
                )

        # v1 and v2 have IDENTICAL embeddings (cosine distance 0); v3 is orthogonal to
        # both (cosine distance 1). Exact, hand-computable expected values.
        v1_vec = _unit_vector(512, 0)
        v2_vec = _unit_vector(512, 0)
        v3_vec = _unit_vector(512, 1)

        with session_scope() as session:
            upsert_video_vision_features(
                session,
                video_id=VIDEO_IDS[0],
                image_embedding=v1_vec,
                clip_clickbait_score=0.0,
                clip_ai_generated_score=0.0,
                clip_text_heavy_score=0.0,
                clip_model="test",
            )
            upsert_video_vision_features(
                session,
                video_id=VIDEO_IDS[1],
                image_embedding=v2_vec,
                clip_clickbait_score=0.0,
                clip_ai_generated_score=0.0,
                clip_text_heavy_score=0.0,
                clip_model="test",
            )
            upsert_video_vision_features(
                session,
                video_id=VIDEO_IDS[2],
                image_embedding=v3_vec,
                clip_clickbait_score=0.0,
                clip_ai_generated_score=0.0,
                clip_text_heavy_score=0.0,
                clip_model="test",
            )
            upsert_video_nlp_features(
                session, video_id=VIDEO_IDS[0], **_nlp_fields(_unit_vector(384, 0))
            )
            upsert_video_nlp_features(
                session, video_id=VIDEO_IDS[1], **_nlp_fields(_unit_vector(384, 0))
            )
            upsert_video_nlp_features(
                session, video_id=VIDEO_IDS[2], **_nlp_fields(_unit_vector(384, 1))
            )

        with session_scope() as session:
            mean_similarity = channel_thumbnail_self_similarity_mean(
                session, VIDEO_IDS[0], TEST_CHANNEL_ID
            )
            # avg(distance(v1,v2)=0, distance(v1,v3)=1) = 0.5
            assert mean_similarity is not None
            assert abs(mean_similarity - 0.5) < 1e-6

            dup_count = near_duplicate_thumbnail_count(session, VIDEO_IDS[0])
            # only v2 is within the near-duplicate threshold of v1
            assert dup_count == 1

            title_similarity = channel_title_self_similarity_mean(
                session, VIDEO_IDS[0], TEST_CHANNEL_ID
            )
            assert title_similarity is not None
            assert abs(title_similarity - 0.5) < 1e-6
    finally:
        _cleanup()


def test_near_duplicate_thumbnail_count_none_without_embedding():
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
                    id=VIDEO_IDS[0],
                    channel_id=TEST_CHANNEL_ID,
                    title="Test Video",
                    published_at=datetime.now(UTC),
                ),
            )

        with session_scope() as session:
            result = near_duplicate_thumbnail_count(session, VIDEO_IDS[0])
        assert result is None
    finally:
        _cleanup()
