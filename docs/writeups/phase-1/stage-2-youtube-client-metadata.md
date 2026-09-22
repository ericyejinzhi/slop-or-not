# Phase 1, Stage 2 — YouTube API client: channel resolution + video metadata

## What is being implemented

A YouTube Data API v3 client for resolving a channel (by id or `@handle`) and pulling its video metadata — no comments, no thumbnails, no DB writes yet. This is the read-only "can we talk to YouTube and get sane data back" stage.

Files: `src/sloppy/ingest/youtube.py` (new), `src/sloppy/cli.py` (adds an `ingest` sub-app with one command, `inspect-channel`), `tests/test_youtube_client.py` (new). Dependency added: `google-api-python-client`.

Key functions in `youtube.py`:
- `get_youtube_client(settings)` — builds the `googleapiclient` service object from `YOUTUBE_API_KEY`.
- `resolve_channel(client, id_or_handle)` — regex-detects a raw channel id (`^UC[\w-]{22}$`) vs. a handle, queries `channels.list` accordingly, returns a `ChannelMeta` pydantic model (title, handle, subscriber/video/view counts, and the cached `uploads_playlist_id`).
- `iter_playlist_video_ids(client, playlist_id)` — paginates `playlistItems.list` (1 quota unit/page) and yields video ids lazily.
- `fetch_videos_metadata(client, video_ids)` — batches ids 50-at-a-time into `videos.list(part="snippet,statistics,contentDetails,topicDetails")` (1 unit per batch of up to 50) and returns `VideoMeta` models, including `duration_seconds` (hand-parsed from ISO 8601 `PT#H#M#S`) and `topic_categories` (Wikipedia URLs).
- `_with_retry(...)` — retries transient errors (403/429/5xx) with exponential backoff, but raises immediately on a genuine `quotaExceeded` reason instead of burning retries.

CLI: `slop ingest inspect-channel <id|handle>` prints the channel's stats and its 5 most recent uploads (title, duration, topic categories) — nothing is written to Postgres or MinIO.

## What it should look like

Running against a real channel should print something like:

```
$ uv run slop ingest inspect-channel @somechannel
Some Channel Name (UCxxxxxxxxxxxxxxxxxxxxxx)
  handle:            @somechannel
  subscribers:       123456
  videos:            842
  uploads playlist:  UUxxxxxxxxxxxxxxxxxxxxxx

Recent uploads:
  - 'Some Recent Video Title'  [612s]  topics: Video_game_culture, Action-adventure_game
  - 'Another Upload'  [1830s]  topics: Film
  ...
```

The title/subscriber count/video count should match what's shown on the real channel page (subscriber count may be rounded/hidden by the creator — that's a YouTube-side thing, not a bug here). Topic categories are YouTube's Wikipedia-based genre tags, not always present.

If `YOUTUBE_API_KEY` is empty in `.env`, the command should fail fast and cleanly:
```
$ uv run slop ingest inspect-channel @somechannel
[FAIL] YOUTUBE_API_KEY is not set in .env
```
(exit code 1, no stack trace) — this is exactly what happened when it was tested in this environment, since no key has been added yet.

## What to look out for

- **No API key is configured yet** (`.env`'s `YOUTUBE_API_KEY` is still blank), so the live-API verification step below has *not* actually been run against real YouTube data in this environment — only the code path, lint, and unit tests have been exercised. Get a key at https://console.cloud.google.com/apis/credentials (enable "YouTube Data API v3") and paste it into `.env` before testing this stage for real.
- `resolve_channel` uses `forHandle=` for anything that isn't a bare `UC...` channel id. This is the current (non-deprecated) Data API v3 parameter for `@handle` lookups. If you pass something that's neither a valid channel id nor a real handle, you'll get a clean `ValueError: No YouTube channel found for '...'`, not a crash.
- Quota accounting: 1 unit per `channels.list` call, 1 unit per `playlistItems.list` page (50 videos/page), 1 unit per `videos.list` call regardless of batch size (up to 50 ids). `inspect-channel` costs roughly 3 units per run (channel lookup + one playlist page + one video-metadata batch). Worth spot-checking against the Google Cloud Console quota dashboard once you have real usage.
- `_with_retry` deliberately does **not** retry `quotaExceeded` — if you hit your daily 10k-unit cap, you'll see an immediate failure rather than three retries burning more time.
- `google-api-python-client` is dynamically built from a discovery document, so there's no static typing on the raw API response — all the parsing/validation happens in `_parse_video`/`resolve_channel`, and pydantic (`ChannelMeta`/`VideoMeta`) is what actually catches shape problems. This was a deliberate trade-off (discussed and confirmed) over hand-rolling raw HTTP calls.
- `search.list` is never used anywhere (100 units/call vs. 1 unit for `playlistItems.list`) — per the roadmap's quota guidance.

## How to run tests properly

```powershell
# 1. Unit tests (no network/API key needed — pure parsing logic)
uv run pytest tests/test_youtube_client.py -v

# 2. Full suite (should still be all green)
uv run pytest

# 3. Lint
uv run ruff check .

# 4. CLI wiring sanity check (no API key needed)
uv run slop ingest --help

# 5. Live verification (REQUIRES a real YOUTUBE_API_KEY in .env — not yet configured here)
uv run slop ingest inspect-channel <a real @handle or channel id>
# Cross-check the printed title/subscriber count/video titles against the real channel page.
# Then check https://console.cloud.google.com/apis/dashboard for quota usage on the YouTube Data API.
```
