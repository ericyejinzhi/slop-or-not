"""Tests sloppy.features.pipeline - the compute-nlp/compute-vision logic extracted from
the CLI (Phase 4) so Prefect tasks (Phase 7) can call it directly. Real model calls
(sentiment/embeddings/CLIP) are monkeypatched to canned values, so this stays fast and
never touches the network - but every DB read/write/filter (only_missing, channel_id,
video_id, limit) goes through the real dev Postgres via the real upsert helpers,
exercising the actual orchestration logic, not a mock of it.
"""

from datetime import UTC, datetime

import numpy as np
from PIL import Image

from sloppy.db.models import (
    Channel,
    Comment,
    Thumbnail,
    Video,
    VideoNlpFeatures,
    VideoVisionFeatures,
)
from sloppy.db.session import session_scope
from sloppy.features import pipeline
from sloppy.features.title_intent import TitleIntentScores
from sloppy.ingest.upsert import upsert_channel, upsert_comment, upsert_thumbnail, upsert_video
from sloppy.ingest.youtube import ChannelMeta, CommentMeta, VideoMeta

TEST_CHANNEL_ID = "UC_test_features_pipeline_channel"
VIDEO_A = "test_features_pipeline_video_a"
VIDEO_B = "test_features_pipeline_video_b"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(VideoNlpFeatures).filter(
            VideoNlpFeatures.video_id.in_([VIDEO_A, VIDEO_B])
        ).delete(synchronize_session=False)
        session.query(VideoVisionFeatures).filter(
            VideoVisionFeatures.video_id.in_([VIDEO_A, VIDEO_B])
        ).delete(synchronize_session=False)
        session.query(Thumbnail).filter(Thumbnail.video_id.in_([VIDEO_A, VIDEO_B])).delete(
            synchronize_session=False
        )
        session.query(Comment).filter(Comment.video_id.in_([VIDEO_A, VIDEO_B])).delete(
            synchronize_session=False
        )
        session.query(Video).filter(Video.id.in_([VIDEO_A, VIDEO_B])).delete(
            synchronize_session=False
        )
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _seed_videos() -> None:
    with session_scope() as session:
        upsert_channel(
            session,
            ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
        )
        for video_id in (VIDEO_A, VIDEO_B):
            upsert_video(
                session,
                VideoMeta(
                    id=video_id,
                    channel_id=TEST_CHANNEL_ID,
                    title=f"Title for {video_id}",
                    published_at=datetime.now(UTC),
                ),
            )
        upsert_comment(
            session,
            CommentMeta(
                id=f"{VIDEO_A}_comment",
                video_id=VIDEO_A,
                text="great video",
                published_at=datetime.now(UTC),
            ),
        )


def _patch_nlp_models(monkeypatch):
    monkeypatch.setattr(pipeline, "score_comments", lambda texts: [0.1] * len(texts))
    monkeypatch.setattr(
        pipeline,
        "embed_texts",
        lambda texts: np.zeros((len(texts), pipeline.EMBEDDING_DIM)),
    )
    monkeypatch.setattr(
        pipeline,
        "score_title_intent",
        lambda title: TitleIntentScores(
            lure_score=0.1, mysterious_score=0.2, transparent_score=0.3
        ),
    )


def _patch_vision_models(monkeypatch):
    monkeypatch.setattr(
        pipeline, "load_thumbnail_image", lambda client, bucket, key: Image.new("RGB", (4, 4))
    )
    monkeypatch.setattr(pipeline, "embed_image", lambda image: np.zeros(512))
    monkeypatch.setattr(
        pipeline,
        "zero_shot_scores",
        lambda image: {
            "clip_clickbait_score": 0.1,
            "clip_ai_generated_score": 0.2,
            "clip_text_heavy_score": 0.3,
        },
    )


def test_compute_nlp_features_processes_matching_videos_and_persists(monkeypatch):
    _cleanup()
    try:
        _seed_videos()
        _patch_nlp_models(monkeypatch)

        processed = pipeline.compute_nlp_features(channel_id=TEST_CHANNEL_ID)

        assert {video_id for video_id, _ in processed} == {VIDEO_A, VIDEO_B}
        with session_scope() as session:
            row_a = session.get(VideoNlpFeatures, VIDEO_A)
            assert row_a is not None
            assert row_a.title_lure_score == 0.1
            assert row_a.comment_count_scored == 1
            row_b = session.get(VideoNlpFeatures, VIDEO_B)
            assert row_b is not None
            assert row_b.comment_count_scored == 0
    finally:
        _cleanup()


def test_compute_nlp_features_video_id_filters_to_one_video(monkeypatch):
    _cleanup()
    try:
        _seed_videos()
        _patch_nlp_models(monkeypatch)

        processed = pipeline.compute_nlp_features(video_id=VIDEO_A)

        assert [video_id for video_id, _ in processed] == [VIDEO_A]
        with session_scope() as session:
            assert session.get(VideoNlpFeatures, VIDEO_B) is None
    finally:
        _cleanup()


def test_compute_nlp_features_only_missing_skips_already_processed(monkeypatch):
    _cleanup()
    try:
        _seed_videos()
        _patch_nlp_models(monkeypatch)
        pipeline.compute_nlp_features(video_id=VIDEO_A)

        processed = pipeline.compute_nlp_features(channel_id=TEST_CHANNEL_ID, only_missing=True)

        assert [video_id for video_id, _ in processed] == [VIDEO_B]
    finally:
        _cleanup()


def test_compute_vision_features_processes_videos_with_thumbnails(monkeypatch):
    _cleanup()
    try:
        _seed_videos()
        _patch_vision_models(monkeypatch)
        with session_scope() as session:
            upsert_thumbnail(
                session,
                video_id=VIDEO_A,
                s3_bucket="thumbnails",
                s3_key=f"{VIDEO_A}.jpg",
                content_type="image/jpeg",
                width=100,
                height=100,
                source_url="https://example.com/thumb.jpg",
                downloaded_at=datetime.now(UTC),
            )
        # VIDEO_B has no thumbnail - should not be selected at all.

        from sloppy.config import Settings

        processed = pipeline.compute_vision_features(
            Settings(_env_file=None), channel_id=TEST_CHANNEL_ID
        )

        assert processed == [VIDEO_A]
        with session_scope() as session:
            row = session.get(VideoVisionFeatures, VIDEO_A)
            assert row is not None
            assert row.clip_clickbait_score == 0.1
    finally:
        _cleanup()


def test_compute_vision_features_only_missing_skips_already_processed(monkeypatch):
    _cleanup()
    try:
        _seed_videos()
        _patch_vision_models(monkeypatch)
        with session_scope() as session:
            for video_id in (VIDEO_A, VIDEO_B):
                upsert_thumbnail(
                    session,
                    video_id=video_id,
                    s3_bucket="thumbnails",
                    s3_key=f"{video_id}.jpg",
                    content_type="image/jpeg",
                    width=100,
                    height=100,
                    source_url="https://example.com/thumb.jpg",
                    downloaded_at=datetime.now(UTC),
                )

        from sloppy.config import Settings

        settings = Settings(_env_file=None)
        pipeline.compute_vision_features(settings, video_id=VIDEO_A)

        processed = pipeline.compute_vision_features(
            settings, channel_id=TEST_CHANNEL_ID, only_missing=True
        )

        assert processed == [VIDEO_B]
    finally:
        _cleanup()
