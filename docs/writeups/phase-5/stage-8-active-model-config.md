# Phase 5, Stage 8 - `Settings` active-model fields + TODO.md

## What is being implemented

Two new fields on `src/sloppy/config.py`'s `Settings`, in a new `# Active model (Phase 5)` group following the file's existing style exactly:

```python
active_model_name: str = ""
active_model_version: str = ""
```

Both default to `""` (not `None`), consistent with `youtube_api_key`/`labeler_name`'s existing "blank means unset" convention. `GET /videos`/`GET /videos/{id}` (Stage 5) treat a blank value the same as an explicit override being absent - they return `score: null`/`predicted_label: null` for every video rather than erroring, since there's no requirement that a model be configured for the API to function.

No API host/port/CORS settings were added - out of scope per the decisions confirmed earlier in this phase (no authentication or rate limiting is required anywhere in the roadmap before Phase 8, and host/port are uvicorn/docker-compose invocation concerns, not application configuration). This is a deliberate omission, not an oversight.

**Note on sequencing**: the plan originally scheduled these two fields for this stage, but the videos router (Stage 5) genuinely needed them to exist to be functional at all, so they were actually added to `config.py` during Stage 5's implementation. This stage's real remaining work is the test and the `TODO.md` documentation below - both were, in fact, still done here as planned.

## What it should look like

```python
>>> from sloppy.config import Settings
>>> Settings(_env_file=None).active_model_name
''
>>> Settings(_env_file=None, active_model_name="xgboost", active_model_version="v1").active_model_name
'xgboost'
```

```
# .env
ACTIVE_MODEL_NAME=xgboost
ACTIVE_MODEL_VERSION=20260101-000000
```

```
$ uv run uvicorn sloppy.api.app:app --reload --port 8000
$ curl http://localhost:8000/videos
# scores are now populated for any video with a video_scores row under that exact
# model_name/model_version, without needing to pass model_name/model_version query params
```

`docs/writeups/TODO.md` gained a new item (15, "Promote a trained model to active") documenting this as a manual step, tiered as "not blocking" (same tier as the existing W&B entry) since the API works completely correctly with these blank.

## What to look out for

- These fields are read fresh from `get_settings()` (process-wide `lru_cache`'d) on every request in the videos router - so changing `.env` requires restarting the `uvicorn` process (or, in a test, calling `get_settings.cache_clear()`) to take effect, same as every other `Settings` field in this project.
- The two new fields are independent - setting only one and leaving the other blank means `_resolve_model` (Stage 5) still treats the model as fully unresolved (`not name or not version` short-circuits), since a model reference genuinely needs both a name and a version to be meaningful.

## How to run tests properly

```powershell
uv run pytest tests/test_config.py -v
uv run pytest    # full suite
uv run ruff check .
```

`test_active_model_defaults_to_unset_and_can_be_overridden` was added to the existing `tests/test_config.py` (not a new file, matching the one-test-file-per-module convention - this file already existed with 2 tests before this phase). Fully pure/fast, no DB or network.
