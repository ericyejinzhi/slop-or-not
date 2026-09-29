# Phase 5, Stage 5 - Pydantic schemas + `videos` router

## What is being implemented

The core read path of the API: `GET /videos` (paginated, filterable, sortable list with scores and thumbnails) and `GET /videos/{video_id}` (full feature breakdown + similar videos). This is the largest single stage of the phase - everything downstream (the React dashboard in Phase 6) will consume these two endpoints directly.

New files:
- `src/sloppy/api/schemas.py` - all Pydantic request/response models for the whole phase (not just this stage, to avoid splitting overlapping shapes across files): `NlpFeatureBreakdown`/`VisionFeatureBreakdown` (`from_attributes=True` mirrors of the scalar, non-vector columns on `VideoNlpFeatures`/`VideoVisionFeatures`), `SimilarVideo`, `VideoListItem`/`VideoListResponse`, `VideoDetail`, plus `IngestRequest`/`IngestResponse`/`LabelCreateRequest`/`LabelResponse` for Stage 6.
- `src/sloppy/api/dependencies.py` - `get_db()` (wraps `session_scope()` as a generator dependency) and `get_s3()` (returns a real boto3 client via `get_s3_client(get_settings())`), injected via `Depends(...)`.
- `src/sloppy/api/routers/videos.py` - `videos_router`, mounted onto the app in `create_app()`.

**One deviation from the original staged plan, made necessary by implementation order**: the plan sequenced `Settings.active_model_name`/`active_model_version` into Stage 8, but this router's `_resolve_model` helper genuinely needs those fields to exist to be functional at all. They were added to `src/sloppy/config.py` now, in this stage, rather than waiting - Stage 8 will still add the dedicated config-defaults test and the `TODO.md` documentation as planned, it just won't be re-adding fields that already exist.

## What it should look like

Against the real dev Postgres + MinIO, with synthetic fixture data (7 videos across 2 channels, one fully-featured video with NLP/vision rows and 2 videos with known thumbnail embeddings for the similarity check, one real thumbnail uploaded to MinIO):

```
$ curl "http://localhost:8000/videos?channel_id=UC_test&model_name=xgboost&model_version=v1&limit=2"
{
  "items": [
    {"id": "video_a", "title": "...", "channel_id": "UC_test", "channel_handle": null,
     "published_at": "...", "view_count": 300, "thumbnail_url": "http://localhost:9000/thumbnails/...",
     "score": 0.9, "predicted_label": "down"},
    {"id": "video_b", "score": null, "predicted_label": null, ...}
  ],
  "total": 6, "limit": 2, "offset": 0
}

$ curl "http://localhost:8000/videos/video_d?model_name=xgboost&model_version=v1"
{
  "id": "video_d", "score": 0.5, "predicted_label": "down",
  "model_name": "xgboost", "model_version": "v1",
  "nlp_features": {"sentiment_mean": 0.2, "title_transparent_score": 0.7, ...},
  "vision_features": {"clip_clickbait_score": 0.3, ...},
  "similar_videos": [
    {"video_id": "video_near", "distance": 0.0, "title": "Video Near", "thumbnail_url": null},
    {"video_id": "video_far", "distance": 1.0, "title": "Video Far", "thumbnail_url": null}
  ]
}
```

All of this was verified for real: 7 new integration tests in `tests/test_api_videos.py`, run through `TestClient` against the real dev Postgres + MinIO with fixture rows inserted via the real upsert helpers - every one passed on the first run. Genuine "does this look right against real videos" is still deferred (no real ingested data exists), but the endpoint logic itself - joins, filters, sorting, pagination, presigned URLs, the similar-videos query - is exercised end to end, not just unit-tested in isolation.

## What to look out for

- **The "no active model" case is handled by a join that matches nothing, not a branch.** `_resolve_model` returns `(None, None)` when neither an override nor `Settings.active_model_name`/`version` is set; the router then substitutes `""` for both in the `VideoScore` join condition. Since no real model is ever persisted under an empty-string name, the outer join simply finds no match and every score/predicted_label comes back `None` uniformly - across both list and detail endpoints, and regardless of sort order. This was a deliberate simplification over branching the query, and it depends on model names/versions always being non-empty in practice (true today, worth re-checking if that ever changes).
- **`GET /videos/{id}`'s 404 is an explicit `session.get(Video, video_id) is None` check**, not reliance on any exception handler (none exists yet - that's Stage 7). Getting this right now means Stage 7's `ValueError`-to-404 handler is purely for the ingest path, not double-duty for video lookups.
- **Similar videos silently drops a neighbor whose `Video` row no longer exists** (a defensive `continue` in the loop) - this should never happen given the FK from `video_vision_features.video_id` to `videos.id`, but the code doesn't assume that invariant holds forever.
- **Presigned thumbnail URLs are genuinely fetchable, verified with real MinIO**, not just asserted to be non-null - `test_list_videos_thumbnail_url_is_genuinely_fetchable` does a real `httpx.get()` against the URL the endpoint returns and checks the bytes match what was uploaded.
- **`tags` defaults to `[]`, not `None`,** in `VideoDetail` even though the underlying `Video.tags` column is nullable - `video.tags or []` in the router absorbs that, so the API never returns a null `tags` array to a consumer.
- Filtering by `predicted_label` effectively requires a matching `VideoScore` row (since the outer join's result is filtered in the `WHERE` clause) - a video with no score for the resolved model is excluded from a `predicted_label`-filtered list, which is the correct behavior (you can't filter by a label that doesn't exist for that video/model pair) but worth remembering since it turns the outer join into inner-join-like behavior only for that query.

## How to run tests properly

```powershell
uv run pytest tests/test_api_videos.py -v
uv run pytest    # full suite
uv run ruff check .
uv run ruff format --check .

# Manual check once real data exists:
uv run uvicorn sloppy.api.app:app --reload --port 8000
curl "http://localhost:8000/videos"
curl "http://localhost:8000/videos/<a real video id>"
```

All 7 tests hit the real dev Postgres and MinIO (`docker compose up -d` required) via `TestClient(app)` - no mocking of the DB or S3 layers, matching the project's established integration-test convention.
