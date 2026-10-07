"""Read-only mode: with Settings.read_only on, the API rejects everything that is not a
GET/HEAD/OPTIONS with a 403 (so a public deployment cannot be used to ingest channels or
write labels), while reads and CORS preflights still work. Each test builds its own app
from explicit Settings, so nothing depends on the real .env."""

import pytest
from fastapi.testclient import TestClient

from sloppy.api.app import create_app
from sloppy.config import Settings


def _client(read_only: bool) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, read_only=read_only)))


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_read_only_rejects_every_write_method_even_on_paths_that_do_not_exist(method):
    # blocked by the middleware before routing, so a future write endpoint is covered too
    response = _client(read_only=True).request(method, "/some/future/endpoint")

    assert response.status_code == 403
    assert response.json() == {"detail": "This deployment is read-only"}


def test_read_only_blocks_the_real_write_endpoints():
    client = _client(read_only=True)

    ingest = client.post("/ingest", json={"channel": "@somechannel"})
    label = client.post("/labels", json={"video_id": "abc", "label": "up"})
    batch = client.post("/labels/batch", json={"channel_id": "UC_x", "label": "up"})

    assert (ingest.status_code, label.status_code, batch.status_code) == (403, 403, 403)


def test_read_only_still_serves_reads_and_reports_itself():
    client = _client(read_only=True)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/config").json() == {"read_only": True}


def test_read_only_does_not_block_cors_preflight_requests():
    response = _client(read_only=True).options("/ingest")

    assert response.status_code != 403


def test_a_writable_app_reaches_the_endpoint_validation_instead_of_a_403():
    client = _client(read_only=False)

    # an empty body is a 422 from the endpoint's own validation, proving no middleware
    # intercepted the request (the endpoint is never actually run)
    assert client.post("/ingest", json={}).status_code == 422
    assert client.get("/config").json() == {"read_only": False}


def test_the_module_level_app_follows_the_environment_setting(monkeypatch):
    monkeypatch.setenv("READ_ONLY", "true")
    from sloppy.config import get_settings

    get_settings.cache_clear()
    try:
        assert TestClient(create_app()).post("/ingest", json={}).status_code == 403
    finally:
        monkeypatch.delenv("READ_ONLY")
        get_settings.cache_clear()
