"""Integration test against real Postgres proving video_vision_features upserts
overwrite in place on video_id - mirrors tests/test_features_nlp_store.py's pattern.
"""

from datetime import UTC, datetime

from sloppy.db.models import Channel, Video, VideoVisionFeatures
from sloppy.db.session import session_scope
from sloppy.features.vision_store import upsert_video_vision_features
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_vision_store_channel"
TEST_VIDEO_ID = "test_vision_store_video_0001"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(VideoVisionFeatures).filter(
            VideoVisionFeatures.video_id == TEST_VIDEO_ID
        ).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _base_fields(**overrides) -> dict:
    fields = {
        "image_embedding": [0.1] * 512,
        "clip_clickbait_score": 0.2,
        "clip_ai_generated_score": 0.1,
        "clip_text_heavy_score": 0.3,
        "clip_model": "openai/clip-vit-base-patch32",
    }
    fields.update(overrides)
    return fields


def test_upsert_video_vision_features_updates_in_place():
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
            upsert_video_vision_features(session, video_id=TEST_VIDEO_ID, **_base_fields())
        with session_scope() as session:
            upsert_video_vision_features(
                session, video_id=TEST_VIDEO_ID, **_base_fields(clip_clickbait_score=0.9)
            )

        with session_scope() as session:
            rows = (
                session.query(VideoVisionFeatures)
                .filter(VideoVisionFeatures.video_id == TEST_VIDEO_ID)
                .all()
            )
            assert len(rows) == 1
            assert rows[0].clip_clickbait_score == 0.9
            assert len(rows[0].image_embedding) == 512
    finally:
        _cleanup()
