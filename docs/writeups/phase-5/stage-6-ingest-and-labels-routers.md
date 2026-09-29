# Phase 5, Stage 6 - `ingest` and `labels` routers

## What is being implemented

Two write-path endpoints: `POST /ingest` (`src/sloppy/api/routers/ingest.py`) and `POST /labels` (`src/sloppy/api/routers/labels.py`), both mounted onto the app in `create_app()`.

`POST /ingest` takes an `IngestRequest` (`channel: str | None`, `video_id: str | None` - a `@model_validator` on the schema enforces that exactly one is set) and a FastAPI `BackgroundTasks` parameter. It schedules either `ingest_channel(settings, request.channel)` or `ingest_video(settings, request.video_id)` (the Stage 2 function) via `background_tasks.add_task(...)` and returns `202 Accepted` immediately with an `IngestResponse`. Per the decision confirmed earlier in this phase, there is no job-id or status-tracking mechanism - failures are only visible via server logs and eventual polling of `GET /videos`. This is a deliberate placeholder; real orchestration (retries, scheduling, persisted job state) is Phase 7's job.

`POST /labels` takes a `LabelCreateRequest` (`video_id`, `labeler: str | None`, `label: Literal["up","down","skip"]`, `notes: str | None`). It resolves `labeler = request.labeler or Settings.labeler_name`, returning `400` if still empty (mirroring the CLI's own ad hoc check, since `record_label` itself validates nothing). It does an explicit `session.get(Video, request.video_id) is None` check, returning `404` for a video that doesn't exist - simpler and more precise than trying to parse a `IntegrityError`'s message for the FK-violation case. It then calls the existing `record_label(...)` and returns `201` with a `LabelResponse` built from the input plus a locally-generated `created_at` (since `record_label` itself returns `None`).

## What it should look like

```
$ curl -X POST http://localhost:8000/ingest -H "Content-Type: application/json" -d '{"video_id": "abc123"}'
# 202 Accepted, immediately
{"status": "accepted", "target": "abc123"}

$ curl -X POST http://localhost:8000/ingest -H "Content-Type: application/json" -d '{"channel": "@x", "video_id": "abc123"}'
# 422 Unprocessable Entity - both fields set, rejected by IngestRequest's model_validator

$ curl -X POST http://localhost:8000/labels -H "Content-Type: application/json" \
    -d '{"video_id": "abc123", "labeler": "alice", "label": "down", "notes": "looks like slop"}'
# 201 Created
{"video_id": "abc123", "labeler": "alice", "label": "down", "notes": "looks like slop", "created_at": "..."}

$ curl -X POST http://localhost:8000/labels -d '{"video_id": "abc123", "label": "sideways"}'
# 422 Unprocessable Entity - Pydantic's Literal rejects it before the DB is ever touched
```

Verified with 4 new tests in `tests/test_api_ingest.py` (monkeypatching `ingest_channel`/`ingest_video` at the router's own imported reference, since real ingestion hits the live YouTube API and can take minutes) and 5 new tests in `tests/test_api_labels.py` (full real-Postgres integration, fixture rows via the real upsert helpers).

## What to look out for

- **`IngestRequest`'s "exactly one of channel/video_id" validation returns 422, not 400.** The original staged plan described this as a 400 case, but since the check lives in a Pydantic `@model_validator` on the request body schema, FastAPI's automatic request-validation machinery catches the raised `ValueError` and returns `422 Unprocessable Entity` before the handler function ever runs - the same mechanism that handles a malformed `Literal` field. This is the more idiomatic FastAPI outcome (consistent with every other body-validation failure) and the tests assert 422, not 400, deliberately deviating from the plan's original assumption.
- **`POST /labels`' 400 (missing labeler) and 404 (missing video) are both explicit `HTTPException` raises in the handler**, not routed through Stage 7's centralized handlers - those two cases are checked before `record_label` is ever called, so no `IntegrityError` is actually produced in either case.
- **`TestClient` runs `BackgroundTasks` synchronously before returning the response** - so `test_api_ingest.py`'s assertions only check *which* function got scheduled with *what* argument, not that the HTTP response genuinely returns before ingestion completes (that's a property of real ASGI execution under uvicorn, not something a synchronous test client can observe).
- **Monkeypatching targets the router module's own imported names** (`sloppy.api.routers.ingest.ingest_channel`/`ingest_video`), not `sloppy.ingest.pipeline`'s originals - because `from sloppy.ingest.pipeline import ingest_channel, ingest_video` binds new names into the router module's namespace, and `background_tasks.add_task(ingest_channel, ...)` at call time looks up whatever `ingest_channel` currently means in *that* module.
- The `test_post_labels_falls_back_to_settings_labeler_name`/`test_post_labels_400_when_no_labeler_available` tests both call `get_settings.cache_clear()` before and after monkeypatching `LABELER_NAME`, since `get_settings()` is process-wide `lru_cache`'d - forgetting the second `cache_clear()` in a `finally` would leak a stale cached `Settings` instance into every later test in the process.

## How to run tests properly

```powershell
uv run pytest tests/test_api_ingest.py tests/test_api_labels.py -v
uv run pytest    # full suite
uv run ruff check .
uv run ruff format --check .
```

`test_api_ingest.py` is fully offline (network calls monkeypatched away). `test_api_labels.py` hits the real dev Postgres (`docker compose up -d` required) via the standard `_cleanup()`-guarded, real-upsert-helper pattern.
