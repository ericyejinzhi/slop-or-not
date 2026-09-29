"""Integration tests against the real dev Postgres + MinIO (docker compose up -d).
Fixture rows are inserted via the real upsert helpers (same code path production
ingestion uses), following the project's standard _cleanup()-guarded pattern. Uses
FastAPI's TestClient (httpx-based) rather than mocking the DB/S3 layers.
"""

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from sloppy.api.app import app
from sloppy.config import get_settings
from sloppy.db.models import (
    Channel,
    Thumbnail,
    Video,
    VideoNlpFeatures,
    VideoScore,
    VideoVisionFeatures,
)
from sloppy.db.session import session_scope
from sloppy.features.nlp_store import upsert_video_nlp_features
from sloppy.features.vision_store import upsert_video_vision_features
from sloppy.ingest.upsert import upsert_channel, upsert_thumbnail, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.models.scores import upsert_video_score
from sloppy.storage import ensure_bucket, get_s3_client

client = TestClient(app)

TEST_CHANNEL_ID = "UC_test_api_videos_channel"
OTHER_CHANNEL_ID = "UC_test_api_videos_other_channel"
VIDEO_A = "test_api_videos_a"  # newest, scored "down"
VIDEO_B = "test_api_videos_b"  # middle, unscored, no features
VIDEO_C = "test_api_videos_c"  # oldest, scored "up"
VIDEO_D = "test_api_videos_d"  # fully-featured detail-test video
VIDEO_NEAR = "test_api_videos_near"  # near-duplicate thumbnail of VIDEO_D
VIDEO_FAR = "test_api_videos_far"  # orthogonal thumbnail to VIDEO_D
OTHER_VIDEO = "test_api_videos_other"  # in OTHER_CHANNEL_ID

ALL_VIDEO_IDS = [VIDEO_A, VIDEO_B, VIDEO_C, VIDEO_D, VIDEO_NEAR, VIDEO_FAR, OTHER_VIDEO]

TEST_MODEL_NAME = "test_model"
TEST_MODEL_VERSION = "v1"
TEST_S3_KEY = "test_api_videos_a.jpg"


def _unit_vector(dim: int, axis: int) -> list[float]:
    vec = [0.0] * dim
    vec[axis] = 1.0
    return vec


def _cleanup() -> None:
    s3_client = get_s3_client(get_settings())
    bucket = get_settings().s3_bucket_thumbnails
    try:
        s3_client.delete_object(Bucket=bucket, Key=TEST_S3_KEY)
    except Exception:  # noqa: BLE001 - best-effort, object may not exist
        pass
    with session_scope() as session:
        session.query(VideoScore).filter(VideoScore.video_id.in_(ALL_VIDEO_IDS)).delete(
            synchronize_session=False
        )
        session.query(VideoNlpFeatures).filter(VideoNlpFeatures.video_id.in_(ALL_VIDEO_IDS)).delete(
            synchronize_session=False
        )
        session.query(VideoVisionFeatures).filter(
            VideoVisionFeatures.video_id.in_(ALL_VIDEO_IDS)
        ).delete(synchronize_session=False)
        session.query(Thumbnail).filter(Thumbnail.video_id.in_(ALL_VIDEO_IDS)).delete(
            synchronize_session=False
        )
        session.query(Video).filter(Video.id.in_(ALL_VIDEO_IDS)).delete(synchronize_session=False)
        session.query(Channel).filter(Channel.id.in_([TEST_CHANNEL_ID, OTHER_CHANNEL_ID])).delete(
            synchronize_session=False
        )


def _seed() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        upsert_channel(
            session,
            ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
        )
        upsert_channel(
            session,
            ChannelMeta(id=OTHER_CHANNEL_ID, title="Other Channel", uploads_playlist_id="UU_y"),
        )
        upsert_video(
            session,
            VideoMeta(
                id=VIDEO_A,
                channel_id=TEST_CHANNEL_ID,
                title="Video A (newest)",
                published_at=now,
                view_count=300,
            ),
        )
        upsert_video(
            session,
            VideoMeta(
                id=VIDEO_B,
                channel_id=TEST_CHANNEL_ID,
                title="Video B (middle)",
                published_at=now - timedelta(days=1),
                view_count=200,
            ),
        )
        upsert_video(
            session,
            VideoMeta(
                id=VIDEO_C,
                channel_id=TEST_CHANNEL_ID,
                title="Video C (oldest)",
                published_at=now - timedelta(days=2),
                view_count=100,
            ),
        )
        upsert_video(
            session,
            VideoMeta(
                id=VIDEO_D,
                channel_id=TEST_CHANNEL_ID,
                title="Video D (full features)",
                published_at=now - timedelta(days=3),
                view_count=50,
                tags=["a", "b"],
            ),
        )
        upsert_video(
            session,
            VideoMeta(
                id=VIDEO_NEAR,
                channel_id=TEST_CHANNEL_ID,
                title="Video Near",
                published_at=now - timedelta(days=4),
            ),
        )
        upsert_video(
            session,
            VideoMeta(
                id=VIDEO_FAR,
                channel_id=TEST_CHANNEL_ID,
                title="Video Far",
                published_at=now - timedelta(days=5),
            ),
        )
        upsert_video(
            session,
            VideoMeta(
                id=OTHER_VIDEO,
                channel_id=OTHER_CHANNEL_ID,
                title="Other Channel Video",
                published_at=now,
            ),
        )

    with session_scope() as session:
        upsert_video_score(
            session,
            video_id=VIDEO_A,
            model_name=TEST_MODEL_NAME,
            model_version=TEST_MODEL_VERSION,
            score=0.9,
            predicted_label="down",
            split="test",
        )
        upsert_video_score(
            session,
            video_id=VIDEO_C,
            model_name=TEST_MODEL_NAME,
            model_version=TEST_MODEL_VERSION,
            score=0.1,
            predicted_label="up",
            split="test",
        )
        upsert_video_score(
            session,
            video_id=VIDEO_D,
            model_name=TEST_MODEL_NAME,
            model_version=TEST_MODEL_VERSION,
            score=0.5,
            predicted_label="down",
            split="test",
        )

    with session_scope() as session:
        upsert_video_nlp_features(
            session,
            video_id=VIDEO_D,
            comment_count_scored=3,
            sentiment_mean=0.2,
            sentiment_std=0.1,
            sentiment_negative_share=0.0,
            slop_keyword_rate=0.0,
            topic_cluster_count=None,
            topic_top_cluster_share=None,
            topic_top_cluster_sentiment=None,
            topic_sentiment_spread=None,
            title_lure_score=0.1,
            title_mysterious_score=0.2,
            title_transparent_score=0.7,
            title_embedding=_unit_vector(384, 0),
            description_embedding=None,
            comment_embedding_mean=None,
            sentiment_model="test",
            embedding_model="test",
        )
        upsert_video_vision_features(
            session,
            video_id=VIDEO_D,
            image_embedding=_unit_vector(512, 0),
            clip_clickbait_score=0.3,
            clip_ai_generated_score=0.4,
            clip_text_heavy_score=0.5,
            clip_model="test",
        )
        upsert_video_vision_features(
            session,
            video_id=VIDEO_NEAR,
            image_embedding=_unit_vector(512, 0),
            clip_clickbait_score=0.0,
            clip_ai_generated_score=0.0,
            clip_text_heavy_score=0.0,
            clip_model="test",
        )
        upsert_video_vision_features(
            session,
            video_id=VIDEO_FAR,
            image_embedding=_unit_vector(512, 1),
            clip_clickbait_score=0.0,
            clip_ai_generated_score=0.0,
            clip_text_heavy_score=0.0,
            clip_model="test",
        )

    settings = get_settings()
    s3_client = get_s3_client(settings)
    ensure_bucket(s3_client, settings.s3_bucket_thumbnails)
    s3_client.put_object(
        Bucket=settings.s3_bucket_thumbnails,
        Key=TEST_S3_KEY,
        Body=b"fake-thumbnail-bytes",
        ContentType="image/jpeg",
    )
    with session_scope() as session:
        upsert_thumbnail(
            session,
            video_id=VIDEO_A,
            s3_bucket=settings.s3_bucket_thumbnails,
            s3_key=TEST_S3_KEY,
            content_type="image/jpeg",
            width=100,
            height=100,
            source_url="https://example.com/thumb.jpg",
            downloaded_at=datetime.now(UTC),
        )


def test_list_videos_default_sort_is_published_at_desc():
    _cleanup()
    _seed()
    try:
        response = client.get(
            "/videos",
            params={
                "channel_id": TEST_CHANNEL_ID,
                "model_name": TEST_MODEL_NAME,
                "model_version": TEST_MODEL_VERSION,
                "limit": 100,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 6  # every TEST_CHANNEL_ID video, OTHER_VIDEO excluded
        ids = [item["id"] for item in body["items"]]
        assert ids == [VIDEO_A, VIDEO_B, VIDEO_C, VIDEO_D, VIDEO_NEAR, VIDEO_FAR]

        video_a = next(item for item in body["items"] if item["id"] == VIDEO_A)
        assert video_a["score"] == 0.9
        assert video_a["predicted_label"] == "down"
        assert video_a["channel_id"] == TEST_CHANNEL_ID

        video_b = next(item for item in body["items"] if item["id"] == VIDEO_B)
        assert video_b["score"] is None
        assert video_b["predicted_label"] is None
    finally:
        _cleanup()


def test_list_videos_filters_by_predicted_label_and_paginates():
    _cleanup()
    _seed()
    try:
        response = client.get(
            "/videos",
            params={
                "channel_id": TEST_CHANNEL_ID,
                "model_name": TEST_MODEL_NAME,
                "model_version": TEST_MODEL_VERSION,
                "predicted_label": "down",
            },
        )
        assert response.status_code == 200
        body = response.json()
        ids = {item["id"] for item in body["items"]}
        assert ids == {VIDEO_A, VIDEO_D}

        paged = client.get(
            "/videos",
            params={"channel_id": TEST_CHANNEL_ID, "limit": 1, "offset": 1},
        )
        assert paged.status_code == 200
        paged_body = paged.json()
        assert paged_body["total"] == 6
        assert len(paged_body["items"]) == 1
        assert paged_body["items"][0]["id"] == VIDEO_B
    finally:
        _cleanup()


def test_list_videos_without_a_resolved_model_returns_null_scores():
    _cleanup()
    _seed()
    try:
        response = client.get("/videos", params={"channel_id": TEST_CHANNEL_ID})
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["score"] is None
            assert item["predicted_label"] is None
    finally:
        _cleanup()


def test_list_videos_thumbnail_url_is_genuinely_fetchable():
    _cleanup()
    _seed()
    try:
        response = client.get("/videos", params={"channel_id": TEST_CHANNEL_ID, "limit": 100})
        video_a = next(item for item in response.json()["items"] if item["id"] == VIDEO_A)
        assert video_a["thumbnail_url"] is not None

        fetched = httpx.get(video_a["thumbnail_url"])
        assert fetched.status_code == 200
        assert fetched.content == b"fake-thumbnail-bytes"
    finally:
        _cleanup()


def test_video_detail_returns_full_feature_breakdown_and_similar_videos():
    _cleanup()
    _seed()
    try:
        response = client.get(
            f"/videos/{VIDEO_D}",
            params={"model_name": TEST_MODEL_NAME, "model_version": TEST_MODEL_VERSION},
        )
        assert response.status_code == 200
        body = response.json()

        assert body["score"] == 0.5
        assert body["predicted_label"] == "down"
        assert body["model_name"] == TEST_MODEL_NAME
        assert body["model_version"] == TEST_MODEL_VERSION
        assert body["tags"] == ["a", "b"]

        assert body["nlp_features"]["sentiment_mean"] == 0.2
        assert body["nlp_features"]["title_transparent_score"] == 0.7
        assert body["vision_features"]["clip_clickbait_score"] == 0.3

        similar_ids = [v["video_id"] for v in body["similar_videos"]]
        assert similar_ids[0] == VIDEO_NEAR  # distance 0 - identical embedding
        assert VIDEO_FAR in similar_ids
        near_entry = body["similar_videos"][0]
        assert abs(near_entry["distance"] - 0.0) < 1e-6
    finally:
        _cleanup()


def test_video_detail_graceful_with_no_features_or_score():
    _cleanup()
    _seed()
    try:
        response = client.get(f"/videos/{VIDEO_B}")
        assert response.status_code == 200
        body = response.json()
        assert body["score"] is None
        assert body["predicted_label"] is None
        assert body["nlp_features"] is None
        assert body["vision_features"] is None
        assert body["thumbnail_url"] is None
        assert body["similar_videos"] == []
    finally:
        _cleanup()


def test_video_detail_404_for_nonexistent_video():
    response = client.get("/videos/does-not-exist")
    assert response.status_code == 404
