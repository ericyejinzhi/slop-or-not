"""POST /ingest's real ingest_channel/ingest_video hit the live YouTube API and can take
minutes - out of scope for a fast automated test. Instead this monkeypatches the router's
own imported references to no-op stubs and asserts the right one gets scheduled with the
right argument. FastAPI's TestClient runs BackgroundTasks synchronously before returning
the response, so "returns before ingestion finishes" is a property of production ASGI
execution this test can't precisely time - it only asserts which function was scheduled.
"""

from fastapi.testclient import TestClient

from sloppy.api import app as app_module
from sloppy.api.routers import ingest as ingest_router_module

client = TestClient(app_module.app)


def test_post_ingest_with_channel_schedules_ingest_channel(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_router_module, "ingest_channel", lambda settings, target: calls.append(target)
    )

    response = client.post("/ingest", json={"channel": "@somechannel"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "target": "@somechannel"}
    assert calls == ["@somechannel"]


def test_post_ingest_with_video_id_schedules_ingest_video(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_router_module, "ingest_video", lambda settings, target: calls.append(target)
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
