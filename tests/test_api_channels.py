"""Integration tests against the real dev Postgres (docker compose up -d)."""

from fastapi.testclient import TestClient

from sloppy.api.app import app
from sloppy.db.models import Channel
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel
from sloppy.ingest.youtube import ChannelMeta

client = TestClient(app)

TEST_CHANNEL_ID = "UC_test_api_channels_channel"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def test_get_channel_detail_returns_channel_stats():
    _cleanup()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(
                    id=TEST_CHANNEL_ID,
                    handle="@testchannel",
                    title="Test Channel",
                    description="A test channel",
                    subscriber_count=1000,
                    video_count=42,
                    view_count=999999,
                    uploads_playlist_id="UU_x",
                ),
            )

        response = client.get(f"/channels/{TEST_CHANNEL_ID}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == TEST_CHANNEL_ID
        assert body["handle"] == "@testchannel"
        assert body["title"] == "Test Channel"
        assert body["subscriber_count"] == 1000
        assert body["video_count"] == 42
        assert body["view_count"] == 999999
        assert body["last_ingested_at"] is None
    finally:
        _cleanup()


def test_get_channel_detail_404_for_nonexistent_channel():
    response = client.get("/channels/does-not-exist")
    assert response.status_code == 404
