# Phase 6, Stage 1 - `GET /channels/{id}` endpoint

## What is being implemented

A small backend addition, ahead of any frontend code: `GET /channels/{channel_id}`, returning a channel's own stats (title, handle, description, subscriber/video/view counts, last-ingested timestamp). This exists because Phase 6's planned "channel view" page needs channel-level data that `GET /videos` never returns (it only carries `channel_handle` per video, not the channel's own row) - confirmed as a genuine gap during planning and addressed with a dedicated new endpoint rather than a workaround, per the decision made with the user.

`src/sloppy/api/schemas.py` gained `ChannelDetail` (a direct `from_attributes=True` mirror of the `Channel` ORM model's scalar columns). `src/sloppy/api/routers/channels.py` is a new, minimal router: one `GET /{channel_id}` handler doing `session.get(Channel, channel_id)`, 404 if missing, `ChannelDetail.model_validate(channel)` otherwise. Mounted onto the app in `create_app()`.

The frontend's channel view page (a later stage) is expected to combine this endpoint (for the header/stats) with the existing `GET /videos?channel_id=<id>` (for the video grid) - deliberately not duplicating pagination/sorting logic in a new endpoint just to nest a video list inside a channel response.

## What it should look like

```
$ curl http://localhost:8000/channels/UC_some_channel
{"id": "UC_some_channel", "handle": "@somechannel", "title": "Some Channel",
 "description": "...", "subscriber_count": 12345, "video_count": 200,
 "view_count": 5000000, "last_ingested_at": "2026-09-20T10:00:00Z"}

$ curl http://localhost:8000/channels/does-not-exist
# 404
{"detail": "Channel 'does-not-exist' not found"}
```

Verified with 2 new tests in `tests/test_api_channels.py`, real Postgres integration via `TestClient`, fixture channel inserted via the real `upsert_channel` helper.

## What to look out for

- This is the smallest possible correct implementation - a single `GET` returning one row, no list, no pagination, no filtering. There was no temptation to over-build here: the video-list functionality already exists and is reused as-is by the frontend rather than re-implemented under `/channels`.
- `last_ingested_at` is `None` for a channel that exists but has never had `ingest_channel` run to completion (the field is only set at the very end of that function) - this is a real, expected state for a freshly-upserted channel, not a bug, and the frontend should render it gracefully (e.g. "never fully ingested" rather than a raw null).
- The 404 message intentionally reuses the exact phrasing style of `GET /videos/{id}`'s 404 (`f"Channel {channel_id!r} not found"`) for consistency across the API's error bodies.

## How to run tests properly

```powershell
uv run pytest tests/test_api_channels.py -v
uv run pytest    # full suite
uv run ruff check .
uv run ruff format --check .
```

Both tests hit the real dev Postgres (`docker compose up -d` required) via `TestClient`, following the standard `_cleanup()`-guarded, real-upsert-helper pattern used throughout this project.
