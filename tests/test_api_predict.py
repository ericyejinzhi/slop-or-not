"""POST /predict at the HTTP layer: the one POST a read-only deployment still serves, its
error mapping, its rate limit, and the proxy-address handling. The prediction itself is
stubbed (tests/test_predict_service.py covers it)."""

import threading

import pytest
from fastapi.testclient import TestClient

from sloppy.api.app import create_app
from sloppy.api.routers import predict as predict_module
from sloppy.config import Settings
from sloppy.predict.errors import InvalidVideoLink, PredictionUnavailable, VideoNotFound
from sloppy.predict.service import ChannelContext, Factor, PredictionResult, SimilarVideo


def _result() -> PredictionResult:
    return PredictionResult(
        video_id="dQw4w9WgXcQ",
        title="A title",
        thumbnail_url="https://img.example/t.jpg",
        score=0.81,
        predicted_label="down",
        factors=[Factor("title_caps_ratio", "Share of the title in capitals", 0.4, 0.9)],
        similar_videos=[SimilarVideo("abc", "Other", 0.12, 0.7)],
        channel=ChannelContext("UC_x", "A Channel", False),
        model_name="xgboost",
        model_version="v1",
        comments_used=12,
        warnings=["note"],
    )


def _client(**settings) -> TestClient:
    values = {"_env_file": None, "read_only": True, "predict_rate_limit_per_hour": 0}
    values.update(settings)
    return TestClient(create_app(Settings(**values)))


@pytest.fixture
def predicting(monkeypatch):
    calls = []

    def fake(settings, link):
        calls.append(link)
        return _result()

    monkeypatch.setattr(predict_module, "predict_video", fake)
    return calls


def test_predict_works_on_a_read_only_deployment_while_other_writes_stay_blocked(predicting):
    client = _client(read_only=True)

    response = client.post("/predict", json={"url": "https://youtu.be/dQw4w9WgXcQ"})

    assert response.status_code == 200
    assert predicting == ["https://youtu.be/dQw4w9WgXcQ"]
    assert client.post("/ingest", json={"channel": "@x"}).status_code == 403
    assert client.post("/labels", json={"video_id": "a", "label": "up"}).status_code == 403
    assert client.post("/predict/anything-else").status_code == 403


def test_the_response_carries_everything_the_page_needs(predicting):
    body = _client().post("/predict", json={"url": "dQw4w9WgXcQ"}).json()

    assert body["score"] == 0.81
    assert body["predicted_label"] == "down"
    assert body["factors"][0] == {
        "feature": "title_caps_ratio",
        "label": "Share of the title in capitals",
        "value": 0.4,
        "contribution": 0.9,
    }
    assert body["similar_videos"][0]["video_id"] == "abc"
    assert body["channel"]["in_dataset"] is False
    assert body["warnings"] == ["note"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (InvalidVideoLink("not a video link"), 422),
        (VideoNotFound("no such video"), 404),
        (PredictionUnavailable("not set up"), 503),
    ],
)
def test_each_failure_maps_to_its_own_status_with_a_readable_message(monkeypatch, error, status):
    def fail(settings, link):
        raise error

    monkeypatch.setattr(predict_module, "predict_video", fail)

    response = _client().post("/predict", json={"url": "x"})

    assert response.status_code == status
    assert response.json() == {"detail": str(error)}


def test_an_empty_or_oversized_url_is_rejected_before_any_work(predicting):
    client = _client()

    assert client.post("/predict", json={"url": ""}).status_code == 422
    assert client.post("/predict", json={"url": "x" * 301}).status_code == 422
    assert client.post("/predict", json={}).status_code == 422
    assert predicting == []


def test_the_rate_limit_applies_per_client_and_says_when_to_retry(predicting):
    client = _client(predict_rate_limit_per_hour=2)

    statuses = [client.post("/predict", json={"url": "a"}).status_code for _ in range(3)]
    refused = client.post("/predict", json={"url": "a"})

    assert statuses == [200, 200, 429]
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0
    assert "Try again" in refused.json()["detail"]
    assert len(predicting) == 2  # refused requests never reach the model


def test_proxy_headers_are_ignored_unless_the_deployment_says_to_trust_them(predicting):
    client = _client(predict_rate_limit_per_hour=1)  # trust_proxy_headers defaults to off

    first = client.post("/predict", json={"url": "a"}, headers={"X-Real-IP": "1.1.1.1"})
    second = client.post("/predict", json={"url": "a"}, headers={"X-Real-IP": "2.2.2.2"})

    # a forged header must not buy a fresh allowance
    assert (first.status_code, second.status_code) == (200, 429)


def test_behind_a_trusted_proxy_each_real_client_gets_its_own_allowance(predicting):
    client = _client(predict_rate_limit_per_hour=1, trust_proxy_headers=True)

    a1 = client.post("/predict", json={"url": "a"}, headers={"X-Real-IP": "1.1.1.1"})
    b1 = client.post("/predict", json={"url": "a"}, headers={"X-Real-IP": "2.2.2.2"})
    a2 = client.post("/predict", json={"url": "a"}, headers={"X-Real-IP": "1.1.1.1"})

    assert (a1.status_code, b1.status_code, a2.status_code) == (200, 200, 429)


def test_a_second_request_while_one_is_running_gets_a_clear_busy_answer(predicting, monkeypatch):
    monkeypatch.setattr(predict_module, "BUSY_WAIT_SECONDS", 0.05)
    app = create_app(Settings(_env_file=None, predict_rate_limit_per_hour=0))
    client = TestClient(app)
    held = threading.Lock()
    held.acquire()
    app.state.predict_lock = held  # simulate a prediction in progress

    response = client.post("/predict", json={"url": "a"})

    assert response.status_code == 503
    assert "still running" in response.json()["detail"]
    assert predicting == []


def test_the_lock_is_released_even_when_the_prediction_fails(monkeypatch):
    def fail(settings, link):
        raise VideoNotFound("gone")

    monkeypatch.setattr(predict_module, "predict_video", fail)
    app = create_app(Settings(_env_file=None, predict_rate_limit_per_hour=0))
    client = TestClient(app)

    assert client.post("/predict", json={"url": "a"}).status_code == 404
    assert app.state.predict_lock.acquire(blocking=False)  # not left locked


def test_config_reports_whether_predictions_can_run():
    off = _client().get("/config").json()
    on = (
        _client(video_only_model_name="xgboost", video_only_model_version="v1", youtube_api_key="k")
        .get("/config")
        .json()
    )
    no_key = (
        _client(video_only_model_name="xgboost", video_only_model_version="v1")
        .get("/config")
        .json()
    )

    assert off["predict_enabled"] is False
    assert on["predict_enabled"] is True
    assert no_key["predict_enabled"] is False
