# Phase 6, Stage 2 - `GET /labels/pool` endpoint

## What is being implemented

A second small backend addition ahead of the frontend: `GET /labels/pool`, exposing Phase 2's existing `candidate_videos`/`sample_pool`/`consistency_sample` functions (`src/sloppy/label/pool.py`) over HTTP, so the web labeling page (a later stage) gets the exact same per-channel-max and corpus-shape guarantees the CLI's `slop label run` already has - not a simplified web-only approximation, per the decision made with the user.

New schemas in `src/sloppy/api/schemas.py`: `LabelPoolItem` (video_id, title, channel_id, channel_handle, published_at, duration_seconds, view_count, like_count, comment_count, thumbnail_url) and `LabelPoolResponse` (`items: list[LabelPoolItem]`). The endpoint itself was added to the existing `src/sloppy/api/routers/labels.py` (same router as `POST /labels`, since both concern "labels" as a resource) rather than a new file - `GET /pool` under the `/labels` prefix.

Query params mirror the CLI's own `slop label run` options: `mode` ("pool" or "consistency"), `per_channel_max`, `pool_size`, `seed`, `consistency_sample_size`. The handler calls the same Phase 2 functions unmodified, then joins in `Video`/`Thumbnail` rows (batched, not per-item) to build the richer `LabelPoolItem` response the web UI needs (the CLI prints title/duration/view-counts directly from a fetched `Video` row per iteration - this endpoint does the equivalent batched, upfront, for the whole pool in one response).

A shared `presigned_thumbnail_url(s3_client, thumbnail)` helper was extracted from `routers/videos.py` into a new `src/sloppy/api/thumbnails.py`, since this endpoint needed the exact same thumbnail-presigning logic `videos.py` already had - avoiding duplicating it a second time.

## What it should look like

```
$ curl "http://localhost:8000/labels/pool?per_channel_max=30&pool_size=50"
{"items": [
  {"video_id": "...", "title": "...", "channel_id": "UC_...", "channel_handle": "@...",
   "published_at": "...", "duration_seconds": 600, "view_count": 1000, "like_count": 50,
   "comment_count": 10, "thumbnail_url": "http://localhost:9000/thumbnails/....jpg?..."},
  ...
]}

$ curl "http://localhost:8000/labels/pool?mode=consistency&consistency_sample_size=20"
# returns previously-labeled (non-skip) videos for a spot-check re-labeling session
```

Verified with 2 new tests appended to `tests/test_api_labels.py`: one confirming labeled-video exclusion and the `per_channel_max` cap interact exactly the way `candidate_videos` already established in Phase 2 (rank-then-exclude, not exclude-then-rank - see below), one confirming `mode=consistency` returns previously-labeled videos.

## What to look out for

- **A test-writing mistake caught during this stage, not a code bug**: the first draft of `test_get_label_pool_excludes_labeled_and_respects_per_channel_max` assumed labeled-video exclusion happened *before* the per-channel-max cap (i.e. "take the top 2 of the remaining unlabeled videos"). The real, already-established `candidate_videos` behavior (unchanged from Phase 2, confirmed by reading its SQL) ranks by recency first via `row_number() OVER (PARTITION BY channel_id ORDER BY published_at DESC)`, caps at `rn <= per_channel_max`, and *only then* additionally filters out labeled ones from that already-capped set - both conditions live in the same `WHERE` clause, not applied sequentially. With 5 videos (days 0-4) and `per_channel_max=2`, the rn<=2 cut keeps videos 0 and 1 only; video 0 is then excluded for being labeled, leaving just video 1 - video 2 never entered consideration even though it's unlabeled, since it didn't make the recency cut. The test assertion was fixed to match this real, pre-existing, deliberate behavior rather than treating it as a bug - worth remembering if the web labeling page's pool ever looks "smaller than expected" once a few recent videos get labeled.
- **The thumbnail-presigning helper move is a pure refactor** - `videos.py`'s three call sites were updated to import from the new shared `thumbnails.py` module instead of a private function, with no behavior change (confirmed by the full suite still passing, including every existing `test_api_videos.py` assertion).
- This endpoint deliberately does not persist anything or track "which pool a client is currently working through" - like the CLI, the pool is a single response the client fetches once and iterates through locally (a later stage's frontend work); re-fetching `/labels/pool` mid-session would produce a different (freshly shuffled, freshly labeled-excluded) pool, same as re-running `slop label run` would.

## How to run tests properly

```powershell
uv run pytest tests/test_api_labels.py tests/test_api_videos.py -v
uv run pytest    # full suite - 158 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .
```

All new tests hit the real dev Postgres (`docker compose up -d` required) via `TestClient`, fixture rows inserted via the real `upsert_channel`/`upsert_video`/`record_label` helpers, following the standard `_cleanup()`-guarded pattern.
