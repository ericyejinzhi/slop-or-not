"""Tests sloppy.refresh's orchestration: which steps run, in what order, with what
arguments, and what each outcome reports. Every business-logic dependency (ingest,
feature computation, scoring) is monkeypatched - those are covered by their own tests;
this checks the wiring, including the two behaviors this module exists for: channel
ingests are always capped, and a refresh runs through to scoring.
"""

import json

import pytest

from sloppy import refresh
from sloppy.config import Settings
from sloppy.ingest.pipeline import DEFAULT_SAMPLE_SIZE, DEFAULT_SAMPLE_WINDOW, IngestSummary
from sloppy.models.train import ALL_FEATURES, METADATA_NUMERIC_FEATURES

ACTIVE = Settings(
    _env_file=None, active_model_name="logistic_regression", active_model_version="v1"
)
NO_MODEL = Settings(_env_file=None)


def test_ingest_channel_sampled_defaults_to_the_random_sample_not_the_whole_history(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        refresh, "ingest_channel", lambda settings, target, **kwargs: captured.update(kwargs)
    )

    refresh.ingest_channel_sampled(NO_MODEL, "@chan")

    assert captured == {
        "sample_window": DEFAULT_SAMPLE_WINDOW,
        "sample_size": DEFAULT_SAMPLE_SIZE,
    }


def test_ingest_channel_sampled_uses_most_recent_n_when_max_videos_is_given(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        refresh, "ingest_channel", lambda settings, target, **kwargs: captured.update(kwargs)
    )

    refresh.ingest_channel_sampled(NO_MODEL, "@chan", max_videos=7)

    assert captured == {"limit": 7}


def test_score_with_active_model_skips_when_no_model_is_configured(monkeypatch):
    monkeypatch.setattr(refresh, "score_videos", lambda **kw: pytest.fail("must not score"))

    scored, reason = refresh.score_with_active_model(NO_MODEL, ["v1"])

    assert scored == []
    assert "no active model" in reason


def test_score_with_active_model_skips_when_there_is_nothing_to_score(monkeypatch):
    monkeypatch.setattr(refresh, "score_videos", lambda **kw: pytest.fail("must not score"))

    scored, reason = refresh.score_with_active_model(ACTIVE, [])

    assert (scored, reason) == ([], "no videos to score")


def test_score_with_active_model_scores_with_the_configured_model(monkeypatch):
    captured = {}

    def fake_score_videos(**kwargs):
        captured.update(kwargs)
        return ["v1", "v2"]

    monkeypatch.setattr(refresh, "score_videos", fake_score_videos)

    scored, reason = refresh.score_with_active_model(ACTIVE, ["v1", "v2"])

    assert (scored, reason) == (["v1", "v2"], None)
    assert captured["model_name"] == "logistic_regression"
    assert captured["model_version"] == "v1"
    assert captured["video_ids"] == ["v1", "v2"]


def _write_model_metadata(root, name, version, features):
    model_dir = root / name / version
    model_dir.mkdir(parents=True)
    (model_dir / "metadata.json").write_text(json.dumps({"features": features}), encoding="utf-8")


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "DEFAULT_MODEL_ARTIFACTS_DIR", tmp_path)
    return tmp_path


def test_a_metadata_only_model_needs_neither_nlp_nor_vision_features(artifacts):
    _write_model_metadata(
        artifacts, "logistic_regression", "v1", METADATA_NUMERIC_FEATURES + ["genre"]
    )
    assert refresh.active_model_feature_needs(ACTIVE) == (False, False)


def test_a_model_using_a_text_feature_needs_the_nlp_step(artifacts):
    _write_model_metadata(
        artifacts, "logistic_regression", "v1", METADATA_NUMERIC_FEATURES + ["sentiment_mean"]
    )
    assert refresh.active_model_feature_needs(ACTIVE) == (True, False)


def test_a_model_using_a_clip_feature_needs_the_vision_step(artifacts):
    _write_model_metadata(
        artifacts, "logistic_regression", "v1", METADATA_NUMERIC_FEATURES + ["clip_clickbait_score"]
    )
    assert refresh.active_model_feature_needs(ACTIVE) == (False, True)


def test_the_full_feature_set_needs_both(artifacts):
    _write_model_metadata(artifacts, "logistic_regression", "v1", ALL_FEATURES)
    assert refresh.active_model_feature_needs(ACTIVE) == (True, True)


def test_unknown_situations_compute_everything_as_before(artifacts):
    # no active model configured
    assert refresh.active_model_feature_needs(NO_MODEL) == (True, True)
    # configured, but the artifact is missing
    assert refresh.active_model_feature_needs(ACTIVE) == (True, True)
    # artifact present but unreadable / malformed
    model_dir = artifacts / "logistic_regression" / "v1"
    model_dir.mkdir(parents=True)
    (model_dir / "metadata.json").write_text("not json", encoding="utf-8")
    assert refresh.active_model_feature_needs(ACTIVE) == (True, True)
    (model_dir / "metadata.json").write_text("{}", encoding="utf-8")  # no "features" key
    assert refresh.active_model_feature_needs(ACTIVE) == (True, True)


def test_refresh_channel_skips_feature_steps_the_active_model_does_not_use(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls, IngestSummary(channel_id="UC_x", videos_upserted=2))
    monkeypatch.setattr(refresh, "active_model_feature_needs", lambda settings: (False, False))

    result = refresh.refresh_channel(ACTIVE, "@chan")

    assert [c[0] for c in calls] == ["ingest", "score"]  # no nlp, no vision
    assert result.features_skipped == ["nlp", "vision"]
    assert (result.nlp_processed, result.vision_processed, result.scored) == (0, 0, 2)


def test_refresh_video_skips_feature_steps_the_active_model_does_not_use(monkeypatch):
    calls = []
    monkeypatch.setattr(
        refresh,
        "ingest_video",
        lambda settings, vid: IngestSummary(channel_id="UC_x", videos_upserted=1),
    )
    monkeypatch.setattr(refresh, "active_model_feature_needs", lambda settings: (False, True))
    monkeypatch.setattr(
        refresh, "compute_nlp_features", lambda **kw: calls.append("nlp") or [("abc", 1)]
    )
    monkeypatch.setattr(
        refresh, "compute_vision_features", lambda settings, **kw: calls.append("vision") or ["abc"]
    )
    monkeypatch.setattr(refresh, "score_videos", lambda **kw: calls.append("score") or ["abc"])

    result = refresh.refresh_video(ACTIVE, "abc")

    assert calls == ["vision", "score"]
    assert result.features_skipped == ["nlp"]


def _patch_pipeline(monkeypatch, calls, summary):
    monkeypatch.setattr(
        refresh,
        "ingest_channel_sampled",
        lambda settings, target, max_videos=None: (
            calls.append(("ingest", target, max_videos)) or summary
        ),
    )
    monkeypatch.setattr(
        refresh,
        "compute_nlp_features",
        lambda **kw: calls.append(("nlp", kw)) or [("v1", 3), ("v2", 0)],
    )
    monkeypatch.setattr(
        refresh,
        "compute_vision_features",
        lambda settings, **kw: calls.append(("vision", kw)) or ["v1"],
    )
    monkeypatch.setattr(refresh, "channel_video_ids", lambda channel_id: ["v1", "v2"])
    monkeypatch.setattr(
        refresh,
        "score_videos",
        lambda **kw: calls.append(("score", kw["video_ids"])) or ["v1", "v2"],
    )


def test_refresh_channel_runs_ingest_features_then_scoring_in_order(monkeypatch):
    calls = []
    _patch_pipeline(
        monkeypatch,
        calls,
        IngestSummary(channel_id="UC_x", videos_upserted=2, errors=["v3: thumbnail failed"]),
    )

    result = refresh.refresh_channel(ACTIVE, "@chan", max_videos=5)

    assert calls == [
        ("ingest", "@chan", 5),
        ("nlp", {"channel_id": "UC_x", "only_missing": True}),
        ("vision", {"channel_id": "UC_x", "only_missing": True}),
        ("score", ["v1", "v2"]),
    ]
    assert result.channel_id == "UC_x"
    assert (result.videos_ingested, result.nlp_processed) == (2, 2)
    assert (result.vision_processed, result.scored) == (1, 2)
    assert result.score_skipped_reason is None
    assert result.errors == ["v3: thumbnail failed"]


def test_refresh_channel_still_ingests_and_computes_features_without_an_active_model(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls, IngestSummary(channel_id="UC_x", videos_upserted=2))

    result = refresh.refresh_channel(NO_MODEL, "@chan")

    assert [c[0] for c in calls] == ["ingest", "nlp", "vision"]  # no scoring call
    assert result.scored == 0
    assert "no active model" in result.score_skipped_reason


def test_refresh_channel_raises_when_the_channel_cannot_be_resolved(monkeypatch):
    monkeypatch.setattr(
        refresh, "ingest_channel_sampled", lambda settings, target, max_videos=None: IngestSummary()
    )
    with pytest.raises(ValueError, match="did not resolve"):
        refresh.refresh_channel(ACTIVE, "@nope")


def test_refresh_video_runs_features_and_scoring_for_that_video(monkeypatch):
    calls = []
    monkeypatch.setattr(
        refresh,
        "ingest_video",
        lambda settings, vid: (
            calls.append(("ingest", vid)) or IngestSummary(channel_id="UC_x", videos_upserted=1)
        ),
    )
    monkeypatch.setattr(
        refresh, "compute_nlp_features", lambda **kw: calls.append(("nlp", kw)) or [("abc", 4)]
    )
    monkeypatch.setattr(
        refresh,
        "compute_vision_features",
        lambda settings, **kw: calls.append(("vision", kw)) or ["abc"],
    )
    monkeypatch.setattr(
        refresh, "score_videos", lambda **kw: calls.append(("score", kw["video_ids"])) or ["abc"]
    )

    result = refresh.refresh_video(ACTIVE, "abc")

    assert calls == [
        ("ingest", "abc"),
        ("nlp", {"video_id": "abc", "only_missing": True}),
        ("vision", {"video_id": "abc", "only_missing": True}),
        ("score", ["abc"]),
    ]
    assert (result.videos_ingested, result.scored) == (1, 1)


def test_refresh_video_stops_early_and_reports_when_ingest_failed(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "ingest_video",
        lambda settings, vid: IngestSummary(channel_id="UC_x", errors=["abc: boom"]),
    )
    monkeypatch.setattr(refresh, "compute_nlp_features", lambda **kw: pytest.fail("no features"))
    monkeypatch.setattr(refresh, "score_videos", lambda **kw: pytest.fail("must not score"))

    result = refresh.refresh_video(ACTIVE, "abc")

    assert result.videos_ingested == 0
    assert result.errors == ["abc: boom"]
