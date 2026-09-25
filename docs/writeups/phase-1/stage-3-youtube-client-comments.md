# Phase 1, Stage 3 - YouTube API client: comments

## What is being implemented

Comment fetching, extending the same `src/sloppy/ingest/youtube.py` module from Stage 2. No DB writes yet - this is still read-only, debug-CLI-only.

- `CommentMeta` (pydantic) - `id`, `video_id`, `author_display_name`, `author_channel_id`, `text`, `like_count`, `reply_count` (the thread's `totalReplyCount` - replies themselves are never stored, only top-level comments), `published_at`.
- `fetch_top_comments(client, video_id, limit=100)` - paginates `commentThreads.list(part="snippet", order="relevance", textFormat="plainText")` until `limit` comments are collected or there's no more data. `order="relevance"` mirrors YouTube's own "Top comments" sort (the alternative, `order="time"`, would be newest-first).
- Comments-disabled handling: if the API returns an `HttpError` with reason `commentsDisabled`, the function logs it and returns `[]` instead of raising - a single video with comments off must not abort an entire channel ingest later in Stage 5.
- CLI: `slop ingest inspect-video <video_id>` - prints the video's metadata (duration, view/like/comment counts) plus its top 5 comments (author, like count, truncated text). No DB writes.

## What it should look like

Against a video with an active comment section:

```
$ uv run slop ingest inspect-video dQw4w9WgXcQ
'Some Video Title' (dQw4w9WgXcQ)
  duration:  212s
  views/likes/comments:  1234567/98765/4321

Top comments:
  - SomeUser (154 likes): this is a great video, really enjoyed it
  - AnotherUser (89 likes): came here from a recommendation, worth it
  ...
```

The comments shown should roughly match what you'd see sorted "Top comments" on the actual youtube.com watch page.

Against a video with comments disabled:

```
$ uv run slop ingest inspect-video <that video's id>
'Some Video Title' (...)
  duration:  ...
  views/likes/comments:  .../.../...

Top comments:
  (none - comments may be disabled, or there are none yet)
```

No crash, no traceback - just an empty result.

## What to look out for

- **Still no live verification possible** - `YOUTUBE_API_KEY` in `.env` is still blank in this environment, so as with Stage 2, only the code path (unit tests, CLI registration, the missing-key guard) has actually been exercised here, not real API responses. `inspect-video dQw4w9WgXcQ` was run and correctly failed with the missing-key message rather than crashing.
- `likeCount` and `totalReplyCount` come back from the Comments API as real integers already (unlike video/channel statistics, which the API returns as numeric *strings*) - `_int_or_none` handles both cases transparently, but if you're ever debugging a type mismatch, that inconsistency in the raw YouTube API is the reason, not a bug here.
- The `commentsDisabled` special-case is narrow on purpose: it only catches that one specific error reason. Any other `HttpError` (auth problems, quota, 5xx) still propagates normally and will surface as a visible failure rather than being silently swallowed.
- `fetch_top_comments` requests `maxResults=min(100, remaining)` per page - for the default `limit=100` this is usually satisfied in a single API call (1 quota unit), only paginating further if YouTube returns fewer than requested and there's more to fetch.
- The `inspect-video` command calls `fetch_top_comments(..., limit=5)`, not 100 - cheaper for a quick manual check. The real ingest pipeline (Stage 5) will use the roadmap's ~100/video budget.

## How to run tests properly

```powershell
# 1. Unit tests for comment parsing (pure logic, no network/API key needed)
uv run pytest tests/test_youtube_client.py -v

# 2. Full suite (should be all green - 13 tests total after this stage)
uv run pytest

# 3. Lint
uv run ruff check .

# 4. CLI wiring sanity check (no API key needed)
uv run slop ingest --help

# 5. Live verification (REQUIRES a real YOUTUBE_API_KEY in .env - not yet configured here)
uv run slop ingest inspect-video <a real video id, one with an active comment section>
# Cross-check the printed comments against the "Top comments" sort on the real watch page.
uv run slop ingest inspect-video <a video id you know has comments disabled>
# Confirm it prints the "(none - comments may be disabled...)" message and exits 0, no crash.
```
