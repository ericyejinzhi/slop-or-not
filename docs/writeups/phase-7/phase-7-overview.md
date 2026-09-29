# Phase 7 - Orchestration with Prefect (full write-up)

This covers the whole of Phase 7 end-to-end. For stage-by-stage detail, see `stage-1-prefect-server.md` through `stage-7-verification.md` in this same directory.

## What is being implemented

Wrapping ingest -> features -> score as a real, retryable, schedulable Prefect flow, per `ROADMAP.md`. This phase turned out to need more than pure orchestration wiring: two genuine capability gaps had to be filled first (an importable, non-CLI-only features pipeline; a way to score already-ingested, unlabeled videos with an existing model) before there was anything meaningful to orchestrate.

Built across seven stages:

1. **Prefect server** - `prefect` added as a dependency; a new `prefect-server` docker-compose service (the official public image, no custom Dockerfile needed) running Prefect's own API/UI at `http://localhost:4200`.
2. **Extracted `compute-nlp`/`compute-vision`** from CLI-only logic into `src/sloppy/features/pipeline.py`, callable directly by Prefect tasks - plus a new `only_missing`/`channel_id` filter so a daily refresh reprocesses only what's new.
3. **Built the missing "score unlabeled videos" capability** - `dataset.py` refactored to share per-video feature assembly between `assemble_dataset` (labeled, for training) and a new `assemble_features_for_video_ids` (unlabeled, for scoring); a new `src/sloppy/models/scoring.py::score_videos` loads a saved model artifact and applies it to arbitrary video ids.
4. **The flow module** (`src/sloppy/flows/refresh.py`) - 4 retryable tasks (ingest, compute-nlp, compute-vision, score) composed into a per-channel flow, plus a parent flow reading `data/seed_channels.csv` (Phase 2's file, reused per the confirmed decision) as the tracked-channels list.
5. **`slop orchestrate` CLI** - manual, in-process flow triggers for testing without needing a deployment.
6. **Scheduled deployment** - `slop orchestrate serve`, using Prefect's `.serve()` (no separate work-pool/worker needed), registering a real daily cron-scheduled deployment.
7. **Real verification** - both roadmap verify-bullet halves genuinely exercised against the live server: a manually-triggered run of the scheduled deployment completing unattended, and a real, unforced (given this environment's actual missing YouTube API key) task failure retrying 3 times with real delays and surfacing as `FAILED` with `run_count: 4` in the server/UI.

## Architecture, end to end

```
data/seed_channels.csv (Phase 2's file, reused as "tracked channels")
        |
        v
refresh_all_tracked_channels_flow  (@flow, sequential per channel - quota-bound)
        |
        v
refresh_channel_flow(id_or_handle)  (@flow, strictly sequential steps)
        |
        +--> ingest_channel_task -------> ingest_channel()          (Phase 1)
        |         (retries=3, 30s)
        |
        +--> compute_nlp_task ----------> compute_nlp_features(only_missing=True)  (Stage 2)
        |         (retries=3, 30s)
        |
        +--> compute_vision_task -------> compute_vision_features(only_missing=True)  (Stage 2)
        |         (retries=3, 30s)
        |
        +--> score_channel_task --------> score_videos()             (Stage 3)
                  (retries=2, 30s)          |
                  skips if no                +--> assemble_features_for_video_ids()
                  ACTIVE_MODEL_NAME/                (dataset.py, shared with training)
                  VERSION configured          +--> loaded model.joblib.predict_proba()
                                              +--> upsert_video_score(split="live")

Triggered by:
  - `slop orchestrate refresh-channel/refresh-all`  (manual, in-process, any time)
  - `slop orchestrate serve`'s daily cron schedule   (unattended, needs serve() running)

Recorded in:
  - prefect-server (docker-compose) - flow/task runs, retries, deployments, schedules
  - http://localhost:4200 - the same data, as a UI
```

## What it should look like

```
$ export PREFECT_API_URL=http://localhost:4200/api
$ uv run slop orchestrate serve &          # leave running for scheduled/unattended runs

$ uv run slop orchestrate refresh-channel @somechannel
channel_id=UC_...
  nlp_processed=12
  vision_processed=11
  scored=0   # 0 until ACTIVE_MODEL_NAME/VERSION are set (docs/writeups/TODO.md item 15)

$ curl -s -X POST http://localhost:4200/api/deployments/filter -d '{}'
# daily-tracked-channels-refresh, cron "0 6 * * *", active=true, status=READY
```

## What to look out for

**Two real, substantial gaps were found and filled, not assumed away**:
1. `compute-nlp`/`compute-vision`'s entire logic lived inside Typer command bodies with no importable entrypoint - fixed in Stage 2 by extracting it to `features/pipeline.py`, verified behavior-preserving by re-running the full suite.
2. Nothing in the codebase could score an unlabeled video with an already-trained model - `assemble_dataset` hard-required a `splits.csv` label. Fixed in Stage 3 by extracting `assemble_dataset`'s shared per-video feature logic and adding `assemble_features_for_video_ids` + `score_videos`. This is arguably the most product-significant addition in this phase - without it, "score" in "ingest -> features -> score" would have been unimplementable for any video that isn't already labeled, which is every newly-ingested video in a real production refresh.

**One real bug caught by a test, not a test-writing mistake**: `score_videos`' first test failed with `FileNotFoundError` because the test assumed `model_name` could be an arbitrary label independent of what was passed to `train_model`/`save_model` - it can't; `save_model` persists under `artifacts_dir/<name>/<version>/`, where `<name>` is literally whatever string was passed to `train_model(name, ...)`. This is a real contract, now documented, that matters directly for `docs/writeups/TODO.md`'s active-model-promotion step: `ACTIVE_MODEL_NAME` must be the exact training name, not a display label.

**One real, previously-unknown library behavior discovered during Stage 7's forced-failure verification**: a blank `YOUTUBE_API_KEY` produces a `DefaultCredentialsError` from `google-api-python-client` (it falls back to attempting Application Default Credentials), not the anticipated HTTP 403 - meaning this particular failure never touches `ingest/youtube.py`'s own internal HTTP-retry logic at all, only Prefect's task-level retry. Worth knowing for anyone debugging a similar error later.

**Design decisions worth remembering**:
- Prefect's `.serve()` was chosen over the work-pool + separate-worker model - simpler, no extra infrastructure, and the `serve()` process itself both hosts the schedule and executes runs. This is a deliberate complexity-matching choice, not a shortcut - Stage 1's initial TODO.md guidance assumed the other model and was corrected in Stage 6 once this was decided.
- `only_missing=True` is hardcoded in the flow's tasks (not a flow parameter) - a daily refresh should always be incremental; reprocessing a channel's entire history on every run was never the intended behavior, so there was no reason to make it configurable per-run.
- `score_channel_task` re-queries a channel's full video-id list rather than threading through only the videos `compute_nlp_task`/`compute_vision_task` just processed - so a channel's older, previously-unscored videos get scored too, once a model becomes active, not just whatever happened to be new in that specific run.
- `data/seed_channels.csv` being empty (real, current project state) is why every real flow-run in this phase's verification either scored 0 videos or found 0 tracked channels - expected and correctly handled (no error), not a sign anything is broken.

**No real ingested/labeled data or trained model exists yet** - the running theme continues. Every stage's automated tests use monkeypatched business logic or a trivial synthetic model; Stage 7's real verification used the real server and real (mis)configuration of this environment rather than synthetic data, since orchestration/scheduling/retry behavior is infrastructure, not something that needs real YouTube data to prove out.

## How to run tests properly

```powershell
# Backend
uv run pytest                    # 177 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .

# Prefect infra
docker compose up -d prefect-server
curl http://localhost:4200/api/health   # expect: true

# Manual flow triggers (no deployment/schedule needed)
export PREFECT_API_URL=http://localhost:4200/api
uv run slop orchestrate refresh-channel <handle-or-id>
uv run slop orchestrate refresh-all

# Scheduled, unattended execution
uv run slop orchestrate serve &          # leave running
uv run prefect deployment run "refresh-all-tracked-channels/daily-tracked-channels-refresh"
# poll http://localhost:4200/api/flow_runs/<uuid> for COMPLETED

# Open http://localhost:4200 in a browser for the flow-run/deployment UI directly
```

## What's next

Phase 7's code is complete; the remaining work is entirely about real data (still blocked on Phase 2's curation/labeling, per `docs/writeups/TODO.md`) and, once real channels exist in `data/seed_channels.csv` and a model is promoted to active, letting the daily schedule actually do something meaningful. Per `ROADMAP.md`, this was the last phase before Phase 8 ("AWS migration + polish") - the whole system (ingest, features, model, API, React dashboard, and now scheduled orchestration) is functionally complete end to end for the first time; what's left is getting real data through it and eventually moving the deployment target from Docker Compose to AWS.
