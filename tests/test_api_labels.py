"""Integration tests against the real dev Postgres (docker compose up -d)."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from sloppy.api.app import app
from sloppy.db.models import Channel, Label, Video
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta

client = TestClient(app)

TEST_CHANNEL_ID = "UC_test_api_labels_channel"
TEST_VIDEO_ID = "test_api_labels_video_0001"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Label).filter(Label.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _seed_video() -> None:
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


def test_post_labels_creates_a_row_with_explicit_labeler():
    _cleanup()
    try:
        _seed_video()
        response = client.post(
            "/labels",
            json={
                "video_id": TEST_VIDEO_ID,
                "labeler": "alice",
                "label": "down",
                "notes": "looks like slop",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["video_id"] == TEST_VIDEO_ID
        assert body["labeler"] == "alice"
        assert body["label"] == "down"
        assert body["notes"] == "looks like slop"

        with session_scope() as session:
            rows = session.query(Label).filter(Label.video_id == TEST_VIDEO_ID).all()
            assert len(rows) == 1
            assert rows[0].labeler == "alice"
            assert rows[0].label == "down"
    finally:
        _cleanup()


def test_post_labels_falls_back_to_settings_labeler_name(monkeypatch):
    _cleanup()
    try:
        _seed_video()
        monkeypatch.setenv("LABELER_NAME", "configured-labeler")
        from sloppy.config import get_settings

        get_settings.cache_clear()
        try:
            response = client.post("/labels", json={"video_id": TEST_VIDEO_ID, "label": "up"})
            assert response.status_code == 201
            assert response.json()["labeler"] == "configured-labeler"
        finally:
            get_settings.cache_clear()
    finally:
        _cleanup()


def test_post_labels_400_when_no_labeler_available(monkeypatch):
    _cleanup()
    try:
        _seed_video()
        monkeypatch.setenv("LABELER_NAME", "")
        from sloppy.config import get_settings

        get_settings.cache_clear()
        try:
            response = client.post("/labels", json={"video_id": TEST_VIDEO_ID, "label": "up"})
            assert response.status_code == 400
        finally:
            get_settings.cache_clear()
    finally:
        _cleanup()


def test_post_labels_404_for_nonexistent_video():
    response = client.post(
        "/labels", json={"video_id": "does-not-exist", "labeler": "alice", "label": "up"}
    )
    assert response.status_code == 404


def test_post_labels_422_for_invalid_label_value():
    _cleanup()
    try:
        _seed_video()
        response = client.post(
            "/labels",
            json={"video_id": TEST_VIDEO_ID, "labeler": "alice", "label": "sideways"},
        )
        assert response.status_code == 422
    finally:
        _cleanup()
