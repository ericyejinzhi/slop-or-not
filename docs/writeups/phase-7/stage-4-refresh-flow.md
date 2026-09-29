# Phase 7, Stage 4 - The Prefect flow module

## What is being implemented

The orchestration layer itself: `src/sloppy/flows/refresh.py`, a new package tying together everything the previous 3 stages built.

Four `@task`-decorated functions, each wrapping one step and each with its own retry policy (`retries=3, retry_delay_seconds=30` for the network/model-heavy steps; `retries=2` for scoring):
- `ingest_channel_task(id_or_handle)` - calls `ingest_channel` (Phase 1), returns the resolved channel id, raises `ValueError` if none was resolved (so the task genuinely fails and can retry/surface, rather than silently returning `None` downstream).
- `compute_nlp_task(channel_id)` - calls `compute_nlp_features(channel_id=..., only_missing=True)` (Stage 2) - only newly-ingested videos get processed, not the channel's whole history every run.
- `compute_vision_task(channel_id)` - same idea, calling `compute_vision_features`.
- `score_channel_task(channel_id)` - checks `Settings.active_model_name`/`active_model_version`; if either is unset, logs and returns `[]` (no error - this is the same graceful "no model yet" degradation the API (Phase 5) and CLI already use). If set, fetches the channel's video ids and calls `score_videos` (Stage 3).

Two `@flow`-decorated functions:
- `refresh_channel_flow(id_or_handle)` - calls the 4 tasks **strictly in sequence** (each depends on the previous step's data existing - there's nothing to compute NLP features for until videos are ingested), returning a small summary dict.
- `refresh_all_tracked_channels_flow(seed_channels_csv=data/seed_channels.csv)` - reads the `handle` column from Phase 2's seed-channels CSV (the confirmed choice for Phase 7's "tracked channels" list) and calls `refresh_channel_flow` once per handle, sequentially (channel ingestion is YouTube-quota-bound, so concurrency here would only burn through quota faster, not finish sooner). Returns `[]` gracefully if the CSV is missing or has no data rows yet - both real, current states of this project.

## What it should look like

```python
>>> from sloppy.flows.refresh import refresh_channel_flow
>>> refresh_channel_flow("@somechannel")
{"channel_id": "UC_...", "nlp_processed": 12, "vision_processed": 11, "scored": 0}
# scored=0 here because no ACTIVE_MODEL_NAME/VERSION is set yet - expected, not a bug
```

Verified with 11 new tests in `tests/test_flows_refresh.py` - every task's `.fn` attribute (Prefect's built-in escape hatch to call the raw, undecorated function with zero engine/server involvement) is exercised directly with its real business-logic dependency monkeypatched: `ingest_channel_task` returns the resolved id and raises when none resolves; `compute_nlp_task`/`compute_vision_task` pass `channel_id`/`only_missing=True` through correctly; `score_channel_task` skips cleanly with no active model, returns empty for a channel with no videos, and scores correctly when a model is configured. The flow itself is tested by monkeypatching all 4 task references and asserting the call order and data flow (`refresh_channel_flow.fn(...)`); the parent flow is tested against real temp CSV files (a real 2-row file, a header-only file, and a missing path).

## What to look out for

- **Every test uses `.fn` and monkeypatches at the module boundary - none of them touch a live Prefect server, and none are slow.** This is deliberate: task/flow orchestration logic (call order, argument passing, graceful-skip conditions) is exactly what unit tests should verify without needing Prefect's actual engine involved - the engine's own retry/scheduling/UI behavior is Prefect's job to have already tested, not this project's. Genuine end-to-end verification (a real flow run recorded in the real server, actually retrying on a forced failure) is deferred to the next 2 stages, which need the real server.
- **`ingest_channel_task` explicitly raises if `IngestSummary.channel_id` is `None`** - this can happen if `resolve_channel` (inside `ingest_channel`) fails to find the channel at all. Without this check, the task would return `None`, and every downstream task would then be scoped to `channel_id=None` (a channel that doesn't exist), silently processing/scoring nothing while reporting success - the explicit raise converts that into a real task failure Prefect can retry and surface, instead of a flow that "succeeds" while doing nothing useful.
- **`score_channel_task` fetches a channel's video ids via a plain SQLAlchemy query (`_channel_video_ids`), not by reusing `compute_nlp_task`/`compute_vision_task`'s return values** - it re-queries the whole channel's videos (not just the ones just processed), so a channel refreshed for the first time after `ACTIVE_MODEL_NAME` gets configured will correctly score every video in that channel that's missing a score, not just whatever happened to be newly-ingested in that specific run. This is a deliberate choice, not an oversight - "only" wiring the freshly-processed video ids through would silently under-score older videos in the channel that were ingested before the active model existed.
- **This module has zero automated coverage of Prefect's actual retry mechanics** (does a task genuinely retry 3 times with a 30-second backoff, does a failure genuinely show up in the UI) - that's real, deferred, deliberately manual verification, covered in Stage 7 of this phase.

## How to run tests properly

```powershell
uv run pytest tests/test_flows_refresh.py -v
uv run pytest    # full suite - 177 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .
```

No live Prefect server or database needed for any of these 11 tests - everything is monkeypatched at the function-reference level, matching the pattern already established for `tests/test_ingest_pipeline_single_video.py` (Phase 5).
