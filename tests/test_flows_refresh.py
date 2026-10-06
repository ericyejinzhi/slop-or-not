"""Tests sloppy.flows.refresh's orchestration logic, fast and without any live Prefect
server or database: every task's `.fn` attribute calls its raw undecorated function
directly (bypassing Prefect's engine entirely), and every business-logic dependency
(ingest_channel, compute_nlp_features, compute_vision_features, score_videos,
_channel_video_ids) is monkeypatched. This tests "does the flow call the right things
with the right arguments in the right order," not the underlying business logic itself
(already covered by tests/test_ingest_pipeline_single_video.py,
tests/test_features_pipeline.py, tests/test_model_scoring.py).
"""

import pytest

from sloppy import refresh as refresh_module
from sloppy.config import Settings
from sloppy.flows import refresh
from sloppy.ingest.pipeline import IngestSummary


def test_ingest_channel_task_returns_resolved_channel_id(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "ingest_channel_sampled",
        lambda settings, target: IngestSummary(
            channel_id="UC_x", videos_upserted=2, comments_upserted=0, thumbnails_upserted=0
        ),
    )
    assert refresh.ingest_channel_task.fn("@somechannel") == "UC_x"


def test_ingest_channel_task_is_capped_not_the_whole_channel_history(monkeypatch):
    # Regression: the flow used to call ingest_channel with no limit/sample, which pulls a
    # channel's entire upload history.
    captured = {}
    monkeypatch.setattr(
        refresh_module,
        "ingest_channel",
        lambda settings, target, **kw: captured.update(kw) or IngestSummary(channel_id="UC_x"),
    )
    monkeypatch.setattr(refresh, "get_settings", lambda: Settings(_env_file=None))

    refresh.ingest_channel_task.fn("@somechannel")

    assert captured and ("limit" in captured or "sample_size" in captured)


def test_ingest_channel_task_raises_when_channel_id_unresolved(monkeypatch):
    monkeypatch.setattr(refresh, "ingest_channel_sampled", lambda settings, target: IngestSummary())
    with pytest.raises(ValueError, match="did not resolve"):
        refresh.ingest_channel_task.fn("@bad-handle")


def test_compute_nlp_task_scopes_to_channel_and_only_missing(monkeypatch):
    captured = {}

    def fake_compute_nlp_features(**kwargs):
        captured.update(kwargs)
        return [("v1", 3), ("v2", 0)]

    monkeypatch.setattr(refresh, "compute_nlp_features", fake_compute_nlp_features)

    result = refresh.compute_nlp_task.fn("UC_x")

    assert captured == {"channel_id": "UC_x", "only_missing": True}
    assert result == ["v1", "v2"]


def test_compute_vision_task_scopes_to_channel_and_only_missing(monkeypatch):
    captured = {}

    def fake_compute_vision_features(settings, **kwargs):
        captured.update(kwargs)
        return ["v1"]

    monkeypatch.setattr(refresh, "compute_vision_features", fake_compute_vision_features)

    result = refresh.compute_vision_task.fn("UC_x")

    assert captured == {"channel_id": "UC_x", "only_missing": True}
    assert result == ["v1"]


def test_score_channel_task_skips_when_no_active_model(monkeypatch):
    monkeypatch.setattr(refresh, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(refresh, "channel_video_ids", lambda channel_id: ["v1"])
    calls = []
    monkeypatch.setattr(refresh_module, "score_videos", lambda **kwargs: calls.append(kwargs))

    result = refresh.score_channel_task.fn("UC_x")

    assert result == []
    assert calls == []


def test_score_channel_task_returns_empty_when_channel_has_no_videos(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "get_settings",
        lambda: Settings(_env_file=None, active_model_name="xgboost", active_model_version="v1"),
    )
    monkeypatch.setattr(refresh, "channel_video_ids", lambda channel_id: [])
    calls = []
    monkeypatch.setattr(refresh_module, "score_videos", lambda **kwargs: calls.append(kwargs))

    result = refresh.score_channel_task.fn("UC_x")

    assert result == []
    assert calls == []


def test_score_channel_task_scores_when_active_model_is_set(monkeypatch):
    monkeypatch.setattr(
        refresh,
        "get_settings",
        lambda: Settings(_env_file=None, active_model_name="xgboost", active_model_version="v1"),
    )
    monkeypatch.setattr(refresh, "channel_video_ids", lambda channel_id: ["v1", "v2"])
    captured = {}

    def fake_score_videos(**kwargs):
        captured.update(kwargs)
        return ["v1", "v2"]

    monkeypatch.setattr(refresh_module, "score_videos", fake_score_videos)

    result = refresh.score_channel_task.fn("UC_x")

    assert result == ["v1", "v2"]
    assert captured["model_name"] == "xgboost"
    assert captured["model_version"] == "v1"
    assert captured["video_ids"] == ["v1", "v2"]


def test_refresh_channel_flow_calls_all_four_steps_in_order(monkeypatch):
    call_order = []

    monkeypatch.setattr(
        refresh,
        "ingest_channel_task",
        lambda target: call_order.append(("ingest", target)) or "UC_x",
    )
    monkeypatch.setattr(
        refresh,
        "compute_nlp_task",
        lambda channel_id: call_order.append(("nlp", channel_id)) or ["v1"],
    )
    monkeypatch.setattr(
        refresh,
        "compute_vision_task",
        lambda channel_id: call_order.append(("vision", channel_id)) or ["v1"],
    )
    monkeypatch.setattr(
        refresh,
        "score_channel_task",
        lambda channel_id: call_order.append(("score", channel_id)) or ["v1"],
    )

    result = refresh.refresh_channel_flow.fn("@somechannel")

    assert call_order == [
        ("ingest", "@somechannel"),
        ("nlp", "UC_x"),
        ("vision", "UC_x"),
        ("score", "UC_x"),
    ]
    assert result == {"channel_id": "UC_x", "nlp_processed": 1, "vision_processed": 1, "scored": 1}


def test_refresh_all_tracked_channels_flow_reads_csv_and_calls_per_channel(tmp_path, monkeypatch):
    csv_path = tmp_path / "seed_channels.csv"
    csv_path.write_text(
        "handle,expected_lean,genre,source_of_discovery,notes\n@a,,,,\n@b,,,,\n",
        encoding="utf-8",
    )
    called = []
    monkeypatch.setattr(
        refresh,
        "refresh_channel_flow",
        lambda handle: (
            called.append(handle)
            or {"channel_id": handle, "nlp_processed": 0, "vision_processed": 0, "scored": 0}
        ),
    )

    results = refresh.refresh_all_tracked_channels_flow.fn(seed_channels_csv=csv_path)

    assert called == ["@a", "@b"]
    assert len(results) == 2


def test_refresh_all_tracked_channels_flow_handles_header_only_csv(tmp_path):
    csv_path = tmp_path / "seed_channels.csv"
    csv_path.write_text("handle,expected_lean,genre,source_of_discovery,notes\n", encoding="utf-8")

    assert refresh.refresh_all_tracked_channels_flow.fn(seed_channels_csv=csv_path) == []


def test_refresh_all_tracked_channels_flow_handles_missing_csv(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    assert refresh.refresh_all_tracked_channels_flow.fn(seed_channels_csv=missing) == []
