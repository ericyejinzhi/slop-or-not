# Phase 5, Stage 2 - Single-video ingest entrypoint

## What is being implemented

A new public function `ingest_video(settings, video_id) -> IngestSummary` in `src/sloppy/ingest/pipeline.py`, alongside the existing whole-channel `ingest_channel`. It's needed because the upcoming `POST /ingest` endpoint (Stage 6, not built yet) must support ingesting a single video by id, and until now the only public entrypoint ingested an entire channel - the only single-video code (`_ingest_video`) is private and expects an already-fetched `VideoMeta` plus pre-built YouTube/S3 clients, not a bare video id.

`ingest_video` is self-contained the same way `ingest_channel` is: it builds its own `youtube`/`s3_client` (not passed a `Session`), fetches the video's metadata via `fetch_videos_metadata`, and raises `ValueError(f"No YouTube video found for {video_id!r}")` if nothing comes back - deliberately the same exception type and "not found" phrasing as `resolve_channel`'s existing not-found case, so a future centralized error handler (Phase 5 Stage 7) can treat both the same way. Before ingesting, it checks whether the video's channel already exists in the `channels` table; if not, it resolves and upserts that channel first, since `_ingest_video` never creates a `Channel` row and the FK constraint on `videos.channel_id` would otherwise fail for a video whose channel has never been ingested. It then delegates to the existing private `_ingest_video` and folds the result into an `IngestSummary` - the same dataclass `ingest_channel` returns, so any future caller (the ingest router, or a Phase 7 Prefect task) can handle both functions' results uniformly.

## What it should look like

Since this hits the real YouTube API for genuine end-to-end verification, that check is deferred (same as every other network-touching function in this project, tracked in `docs/writeups/TODO.md`). What was verified for real is the orchestration logic itself, fully offline: `get_youtube_client`, `fetch_videos_metadata`, `fetch_top_comments`, `resolve_channel`, `get_s3_client`, `ensure_bucket`, and `extract_thumbnail_url` (all imported directly into `pipeline.py`'s namespace) are monkeypatched to canned/no-op behavior, so the test never touches the network - only the real dev Postgres for the DB side.

```python
>>> summary = ingest_video(settings, "some_real_video_id")
>>> summary
IngestSummary(channel_id='UC...', videos_upserted=1, comments_upserted=0, thumbnails_upserted=0, errors=[])
```

Three scenarios were exercised against the real dev Postgres with fixture rows:
1. Channel already exists in the DB -> `resolve_channel` is never called, `videos_upserted == 1`.
2. Channel doesn't exist yet -> `resolve_channel` is called, the channel is upserted first, then the video, both confirmed present via `session.get(...)`.
3. `fetch_videos_metadata` returns an empty list (video not found on YouTube) -> `ValueError` raised, nothing written to the DB.

## What to look out for

- **Thumbnail extraction is monkeypatched to fail on purpose, not stubbed to succeed.** `_ingest_video`'s existing try/except around `extract_thumbnail_url`/`download_thumbnail_bytes`/`upload_thumbnail` already tolerates a thumbnail failure gracefully (the video and its comments still upsert; only the thumbnail row is skipped) - so making `extract_thumbnail_url` raise a synthetic `RuntimeError` in the test exercises that existing tolerance path directly, without needing to fake yt-dlp or a real image download. This is a deliberate choice to reuse existing, already-tested tolerance rather than build new mocking machinery for the happy path.
- **There is still no test file at all for `ingest_channel` itself** - `pipeline.py` had zero test coverage before this stage (confirmed by checking `tests/` directly; no `test_ingest_pipeline.py` or similar existed). This stage's new `tests/test_ingest_pipeline_single_video.py` establishes the monkeypatching pattern from scratch rather than mirroring an existing one - worth knowing if `ingest_channel` itself ever gets test coverage later, since it could reasonably reuse the same `_patch_network`-style helper introduced here.
- `ingest_video` wraps the call to `_ingest_video` in a try/except mirroring `ingest_channel`'s per-video loop (logs a warning, appends to `summary.errors`, returns rather than raising) - so a single video's unexpected failure behaves consistently whether it's ingested as part of a whole channel or on its own via the new function.
- The novel-channel branch does one extra `session.get(Channel, ...)` round-trip before deciding whether to call `resolve_channel` - a small, deliberate YouTube-quota-saving check (resolving a channel costs an API call) rather than always resolving and relying on the upsert to no-op.

## How to run tests properly

```powershell
uv run pytest tests/test_ingest_pipeline_single_video.py -v
uv run pytest    # full suite - 131 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .
```

All 3 tests are fast and fully offline (no real YouTube API calls) but do hit the real dev Postgres (`docker compose up -d` must be running) via the standard `_cleanup()`-guarded, real-upsert-helper pattern used throughout this project.
