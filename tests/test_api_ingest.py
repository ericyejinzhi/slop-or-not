"""POST /ingest's real refresh_channel/refresh_video (ingest -> features -> score) hit the
live YouTube API and load ML models, taking minutes - out of scope for a fast automated
test. Instead this monkeypatches the router's own imported references to no-op stubs and
asserts the right one gets scheduled with the right arguments. FastAPI's TestClient runs
BackgroundTasks synchronously before returning the response, so "returns before
ingestion finishes" is a property of production ASGI execution this test can't precisely
time - it only asserts which function was scheduled.
"""

from fastapi.testclient import TestClient

from sloppy.api import app as app_module
from sloppy.api.routers import ingest as ingest_router_module

client = TestClient(app_module.app)


def test_post_ingest_with_channel_schedules_a_capped_channel_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_router_module,
        "refresh_channel",
        lambda settings, target, max_videos=None: calls.append((target, max_videos)),
    )

    response = client.post("/ingest", json={"channel": "@somechannel"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "target": "@somechannel"}
    # max_videos=None means "the default random sample" downstream - never "everything"
    assert calls == [("@somechannel", None)]


def test_post_ingest_passes_max_videos_through_for_a_channel(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_router_module,
        "refresh_channel",
        lambda settings, target, max_videos=None: calls.append((target, max_videos)),
    )

    response = client.post("/ingest", json={"channel": "@somechannel", "max_videos": 15})

    assert response.status_code == 202
    assert calls == [("@somechannel", 15)]


def test_post_ingest_rejects_max_videos_outside_the_allowed_range():
    assert client.post("/ingest", json={"channel": "@x", "max_videos": 0}).status_code == 422
    assert client.post("/ingest", json={"channel": "@x", "max_videos": 101}).status_code == 422


def test_post_ingest_rejects_max_videos_for_a_single_video():
    response = client.post("/ingest", json={"video_id": "abc123", "max_videos": 5})
    assert response.status_code == 422


def test_a_failing_background_refresh_is_logged_not_raised(monkeypatch, caplog):
    def boom(settings, target, max_videos=None):
        raise RuntimeError("youtube is down")

    monkeypatch.setattr(ingest_router_module, "refresh_channel", boom)

    response = client.post("/ingest", json={"channel": "@somechannel"})

    assert response.status_code == 202
    assert "Background refresh failed for channel '@somechannel'" in caplog.text


def test_post_ingest_with_video_id_schedules_a_video_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_router_module, "refresh_video", lambda settings, target: calls.append(target)
    )

    response = client.post("/ingest", json={"video_id": "abc123"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "target": "abc123"}
    assert calls == ["abc123"]


def test_post_ingest_rejects_both_channel_and_video_id():
    response = client.post("/ingest", json={"channel": "@x", "video_id": "abc123"})
    assert response.status_code == 422


def test_post_ingest_rejects_neither_channel_nor_video_id():
    response = client.post("/ingest", json={})
    assert response.status_code == 422
