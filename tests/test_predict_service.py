"""predict_video end to end with YouTube, the thumbnail download and the ML models stubbed
out (they need network and minutes of CPU), but the real feature code, the real saved
model file and the real database for the read-only lookups.

The property that matters most is the one asserted in the first test: a prediction leaves
the dataset exactly as it was.
"""

import io
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response
from PIL import Image
from sqlalchemy import text

from sloppy.config import Settings
from sloppy.db.session import session_scope
from sloppy.features.pipeline import NlpFeatureValues
from sloppy.ingest.youtube import VideoMeta
from sloppy.models.train import CHANNEL_CONTEXT_FEATURES, FEATURE_GROUPS, save_model, train_model
from sloppy.predict import service
from sloppy.predict.errors import InvalidVideoLink, PredictionUnavailable, VideoNotFound

VIDEO_ID = "dQw4w9WgXcQ"

# Every table a prediction could conceivably write to.
TABLES = (
    "channels",
    "videos",
    "comments",
    "thumbnails",
    "labels",
    "video_scores",
    "video_nlp_features",
    "video_vision_features",
)


def _row_counts() -> dict[str, int]:
    with session_scope() as session:
        return {t: session.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABLES}


def _toy_training_frame(numeric: list[str], categorical: list[str], n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    frame = pd.DataFrame({c: rng.normal(size=n) for c in numeric})
    for c in categorical:
        frame[c] = rng.choice(["a", "b"], size=n)
    frame["y"] = (frame[numeric[0]] > 0).astype(int)
    return frame


def _save_toy_model(tmp_path, features: str = "video_only", name: str = "logistic_regression"):
    numeric, categorical = FEATURE_GROUPS[features]
    trained = train_model(name, _toy_training_frame(numeric, categorical), numeric, categorical)
    save_model(trained, tmp_path, train_row_count=200, feature_group=features)
    return trained


def _settings(trained, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "youtube_api_key": "test-key",
        "video_only_model_name": trained.name,
        "video_only_model_version": trained.version,
    }
    values.update(overrides)
    return Settings(**values)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def _unit_vector() -> np.ndarray:
    vector = np.zeros(512)
    vector[3] = 1.0
    return vector


@pytest.fixture
def stubbed(monkeypatch):
    """Replace everything that touches YouTube, the network or a large model. Returns a
    namespace whose attributes the tests can override before calling predict_video."""
    state = SimpleNamespace(
        meta=VideoMeta(
            id=VIDEO_ID,
            channel_id="UC_not_in_the_dataset_xx",
            title="You Won't BELIEVE This...",
            description="desc",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            duration_seconds=600,
            view_count=1000,
            like_count=50,
            comment_count=20,
            topic_categories=["https://en.wikipedia.org/wiki/Music"],
            tags=["a", "b"],
            thumbnail_url="https://img.example/t.jpg",
        ),
        comments=[SimpleNamespace(text="nice"), SimpleNamespace(text="slop")],
        found=True,
        embed_calls=0,
        thumbnail_ok=True,
    )

    monkeypatch.setattr(service, "get_youtube_client", lambda settings: object())
    monkeypatch.setattr(
        service,
        "fetch_videos_metadata",
        lambda client, ids: [state.meta] if state.found else [],
    )
    monkeypatch.setattr(
        service, "fetch_top_comments", lambda client, video_id, limit: state.comments
    )
    monkeypatch.setattr(
        service, "resolve_channel", lambda client, channel_id: SimpleNamespace(title="A Channel")
    )
    monkeypatch.setattr(
        service, "extract_thumbnail_url", lambda video_id: SimpleNamespace(url="https://x/y.jpg")
    )

    def download(url):
        if not state.thumbnail_ok:
            raise OSError("no thumbnail")
        return _png_bytes(), "image/png"

    monkeypatch.setattr(service, "download_thumbnail_bytes", download)
    monkeypatch.setattr(
        service,
        "nlp_feature_values",
        lambda title, description, comments: NlpFeatureValues(
            comment_count_scored=len(comments),
            sentiment_mean=0.1,
            sentiment_std=0.2,
            sentiment_negative_share=0.3,
            slop_keyword_rate=0.0,
            topic_cluster_count=2,
            topic_top_cluster_share=0.6,
            topic_top_cluster_sentiment=0.1,
            topic_sentiment_spread=0.2,
            title_lure_score=0.7,
            title_mysterious_score=0.4,
            title_transparent_score=0.2,
            title_embedding=[0.0],
            description_embedding=None,
            comment_embedding_mean=None,
        ),
    )

    def embed(image):
        state.embed_calls += 1
        return _unit_vector()

    monkeypatch.setattr(service, "embed_image", embed)
    monkeypatch.setattr(
        service,
        "zero_shot_scores",
        lambda image: {
            "clip_clickbait_score": 0.2,
            "clip_ai_generated_score": 0.1,
            "clip_text_heavy_score": 0.3,
        },
    )
    return state


def test_a_prediction_returns_a_verdict_and_changes_nothing_in_the_dataset(
    tmp_path, stubbed, monkeypatch
):
    trained = _save_toy_model(tmp_path)
    # Object storage must not be touched at all: no thumbnail upload, no model publish.
    monkeypatch.setattr(
        "sloppy.storage.get_s3_client", lambda *a, **k: pytest.fail("a prediction used S3")
    )
    before = _row_counts()

    result = service.predict_video(_settings(trained), f"https://youtu.be/{VIDEO_ID}", tmp_path)

    assert _row_counts() == before
    assert result.video_id == VIDEO_ID
    assert 0.0 <= result.score <= 1.0
    assert result.predicted_label == ("down" if result.score >= 0.5 else "up")
    assert result.model_name == trained.name
    assert result.model_version == trained.version
    assert result.comments_used == 2
    assert 1 <= len(result.factors) <= service.TOP_FACTORS
    contributions = [abs(f.contribution) for f in result.factors]
    assert contributions == sorted(contributions, reverse=True)
    assert result.warnings == []
    assert result.channel.title == "A Channel"
    assert result.channel.in_dataset is False
    assert result.channel.channel_score is None


def test_similar_videos_come_from_the_stored_thumbnails_without_including_the_video(
    tmp_path, stubbed
):
    trained = _save_toy_model(tmp_path)
    with session_scope() as session:
        stored = session.execute(text("SELECT count(*) FROM video_vision_features")).scalar()

    result = service.predict_video(_settings(trained), VIDEO_ID, tmp_path)

    assert len(result.similar_videos) == min(service.SIMILAR_VIDEOS, stored)
    assert all(v.video_id != VIDEO_ID for v in result.similar_videos)
    distances = [v.distance for v in result.similar_videos]
    assert distances == sorted(distances)


def test_a_channel_already_in_the_dataset_is_recognised(tmp_path, stubbed):
    with session_scope() as session:
        known_channel = session.execute(text("SELECT id FROM channels LIMIT 1")).scalar()
    if known_channel is None:
        pytest.skip("needs at least one stored channel")
    stubbed.meta = stubbed.meta.model_copy(update={"channel_id": known_channel})
    trained = _save_toy_model(tmp_path)

    result = service.predict_video(_settings(trained), VIDEO_ID, tmp_path)

    assert result.channel.in_dataset is True
    # this throwaway model has scored nothing, so there is nothing to average yet
    assert result.channel.channel_score is None
    assert result.channel.scored_video_count == 0


def test_a_video_without_comments_still_gets_a_prediction_and_a_warning(tmp_path, stubbed):
    stubbed.comments = []
    trained = _save_toy_model(tmp_path)

    result = service.predict_video(_settings(trained), VIDEO_ID, tmp_path)

    assert result.comments_used == 0
    assert any("no comments" in w for w in result.warnings)


def test_a_thumbnail_that_cannot_be_fetched_degrades_instead_of_failing(tmp_path, stubbed):
    stubbed.thumbnail_ok = False
    trained = _save_toy_model(tmp_path)

    result = service.predict_video(_settings(trained), VIDEO_ID, tmp_path)

    assert stubbed.embed_calls == 0
    assert result.similar_videos == []
    assert any("thumbnail" in w for w in result.warnings)
    assert 0.0 <= result.score <= 1.0


def test_an_unknown_video_is_reported_as_not_found(tmp_path, stubbed):
    stubbed.found = False
    trained = _save_toy_model(tmp_path)

    with pytest.raises(VideoNotFound):
        service.predict_video(_settings(trained), VIDEO_ID, tmp_path)


def test_a_bad_link_is_refused_before_anything_is_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr(
        service, "get_youtube_client", lambda s: pytest.fail("fetched for a bad link")
    )
    trained = _save_toy_model(tmp_path)

    with pytest.raises(InvalidVideoLink):
        service.predict_video(_settings(trained), "https://example.com/not-youtube", tmp_path)


def test_a_youtube_outage_is_reported_as_unavailable(tmp_path, stubbed, monkeypatch):
    def broken(client, ids):
        raise HttpError(Response({"status": "403"}), b"quota")

    monkeypatch.setattr(service, "fetch_videos_metadata", broken)
    trained = _save_toy_model(tmp_path)

    with pytest.raises(PredictionUnavailable, match="YouTube"):
        service.predict_video(_settings(trained), VIDEO_ID, tmp_path)


def test_no_configured_model_means_predictions_are_unavailable(tmp_path, stubbed):
    settings = Settings(_env_file=None, youtube_api_key="k")

    with pytest.raises(PredictionUnavailable, match="not set up"):
        service.predict_video(settings, VIDEO_ID, tmp_path)


def test_no_youtube_key_means_predictions_are_unavailable(tmp_path, stubbed):
    trained = _save_toy_model(tmp_path)

    with pytest.raises(PredictionUnavailable, match="not set up"):
        service.predict_video(_settings(trained, youtube_api_key=""), VIDEO_ID, tmp_path)


def test_a_model_that_needs_channel_history_is_refused(tmp_path, stubbed):
    trained = _save_toy_model(tmp_path, features="all")

    with pytest.raises(PredictionUnavailable, match="channel history"):
        service.predict_video(_settings(trained), VIDEO_ID, tmp_path)


def test_the_video_only_group_really_excludes_the_channel_features():
    numeric, categorical = FEATURE_GROUPS["video_only"]
    assert not set(CHANNEL_CONTEXT_FEATURES) & set(numeric + categorical)
