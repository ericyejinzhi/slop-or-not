"""Integration tests against the real dev Postgres (docker compose up -d)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from sloppy.api.app import app
from sloppy.db.models import Channel, Label, Video
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.label.labels import record_label

client = TestClient(app)

TEST_CHANNEL_ID = "UC_test_api_labels_channel"
TEST_VIDEO_ID = "test_api_labels_video_0001"

POOL_CHANNEL_ID = "UC_test_api_labels_pool_channel"
POOL_VIDEO_PREFIX = "test_api_labels_pool_video_"


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


def _cleanup_pool() -> None:
    with session_scope() as session:
        video_ids = [
            row[0] for row in session.query(Video.id).filter(Video.channel_id == POOL_CHANNEL_ID)
        ]
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Video).filter(Video.channel_id == POOL_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == POOL_CHANNEL_ID).delete()


def test_get_label_pool_excludes_labeled_and_respects_per_channel_max():
    _cleanup_pool()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(
                    id=POOL_CHANNEL_ID,
                    handle="@poolchannel",
                    title="Pool Channel",
                    uploads_playlist_id="UU_x",
                ),
            )
            now = datetime.now(UTC)
            for i in range(5):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{POOL_VIDEO_PREFIX}{i}",
                        channel_id=POOL_CHANNEL_ID,
                        title=f"Pool Video {i}",
                        published_at=now - timedelta(days=i),
                    ),
                )
        with session_scope() as session:
            record_label(session, video_id=f"{POOL_VIDEO_PREFIX}0", labeler="t", label="up")

        response = client.get("/labels/pool", params={"per_channel_max": 2, "pool_size": 100})
        assert response.status_code == 200
        items = response.json()["items"]
        this_channel = [i for i in items if i["channel_id"] == POOL_CHANNEL_ID]
        # candidate_videos ranks by recency FIRST (per_channel_max=2 keeps videos 0 and
        # 1, the 2 most recent), THEN excludes labeled ones from that already-capped set
        # - video 0 is labeled and drops out, leaving only video 1. Video 2 never enters
        # consideration even though it's unlabeled, since it didn't make the rn<=2 cut.
        assert {i["video_id"] for i in this_channel} == {f"{POOL_VIDEO_PREFIX}1"}
        assert all(i["title"].startswith("Pool Video") for i in this_channel)
        assert all(i["channel_handle"] == "@poolchannel" for i in this_channel)
    finally:
        _cleanup_pool()


def test_get_label_pool_consistency_mode_returns_labeled_videos():
    _cleanup_pool()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=POOL_CHANNEL_ID, title="Pool Channel", uploads_playlist_id="UU_x"),
            )
            upsert_video(
                session,
                VideoMeta(
                    id=f"{POOL_VIDEO_PREFIX}0",
                    channel_id=POOL_CHANNEL_ID,
                    title="Pool Video 0",
                    published_at=datetime.now(UTC),
                ),
            )
        with session_scope() as session:
            record_label(session, video_id=f"{POOL_VIDEO_PREFIX}0", labeler="t", label="up")

        response = client.get("/labels/pool", params={"mode": "consistency"})
        assert response.status_code == 200
        video_ids = {item["video_id"] for item in response.json()["items"]}
        assert f"{POOL_VIDEO_PREFIX}0" in video_ids
    finally:
        _cleanup_pool()
