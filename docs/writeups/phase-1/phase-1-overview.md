# Phase 1 - Ingestion (full write-up)

This covers the whole of Phase 1 end-to-end. For stage-by-stage detail, see `stage-1-db-schema.md` through `stage-5-cli-orchestration-upsert.md` in this same directory.

## What is being implemented

A complete pipeline that turns a YouTube channel into real rows in Postgres and real images in MinIO: given a channel id or `@handle`, it resolves the channel, walks its uploads playlist, and for every video pulls metadata, top comments, and a thumbnail - storing all of it idempotently so the same command can be re-run safely (e.g. daily, or after a failure) without duplicating data.

Built across five stages:

1. **DB schema** (`src/sloppy/db/`) - SQLAlchemy 2.0 models for `channels`, `videos`, `comments`, `thumbnails`, plus Alembic migrations.
2. **YouTube client: metadata** (`src/sloppy/ingest/youtube.py`) - channel resolution (id or handle), paginated uploads-playlist walking, batched video metadata fetching.
3. **YouTube client: comments** (same file) - top-comment fetching per video, tolerant of comments-disabled videos.
4. **Thumbnails** (`src/sloppy/ingest/thumbnails.py`) - yt-dlp-based thumbnail URL extraction (no video download), fetch, upload to MinIO.
5. **Orchestration + upsert** (`src/sloppy/ingest/pipeline.py`, `upsert.py`) - ties it all together into `slop ingest channel <id|handle>`, with per-table `ON CONFLICT DO UPDATE` upserts keyed on YouTube's own ids.

Debug commands built along the way (`slop ingest inspect-channel`, `inspect-video`, `inspect-thumbnail`) let each piece be checked in isolation before the real `slop ingest channel` command existed - those remain in the CLI as standalone diagnostics.

## Architecture, end to end

```
slop ingest channel <id|handle>
        │
        ├─ resolve_channel()              (youtube.py)  ──▶ upsert_channel()        (upsert.py)
        │
        ├─ iter_playlist_video_ids()      (youtube.py)  - paginated, 1 unit/page
        │
        ├─ fetch_videos_metadata()        (youtube.py)  - batched 50/call
        │       │
        │       ▼  per video:
        │   ┌─ fetch_top_comments()       (youtube.py)  - tolerant of comments-disabled
        │   ├─ extract_thumbnail_url()    (thumbnails.py) - yt-dlp, metadata only
        │   ├─ download_thumbnail_bytes() (thumbnails.py)
        │   ├─ upload_thumbnail()         (thumbnails.py) ──▶ MinIO `thumbnails` bucket
        │   └─ [one DB transaction] upsert_video + upsert_comment(×N) + upsert_thumbnail
        │
        └─ set channel.last_ingested_at
```

Every table's primary key is YouTube's own id (channel id, video id, comment id; `video_id` for the 1:1 `thumbnails` table) - this is what makes re-running the whole thing safe: every write is `INSERT ... ON CONFLICT DO UPDATE`, never a fresh row.

## What it should look like

A full run against a real channel:

```
$ uv run slop ingest channel @somechannel
Ingested channel UCxxxxxxxxxxxxxxxxxxxxxx
  videos upserted:     47
  comments upserted:   3210
  thumbnails upserted: 46

1 issue(s):
  - abc123XYZ00: thumbnail failed: No thumbnail with known dimensions available
```

After that, per the roadmap's own Phase 1 checkpoint:

- `SELECT count(*) FROM channels/videos/comments/thumbnails;` - sane counts (thumbnails ≈ videos; comments up to ~100×videos, less for comments-disabled ones).
- `SELECT id, title, duration_seconds, topic_categories FROM videos LIMIT 10;` - real titles, plausible durations, genre tags from YouTube's `topicDetails`.
- MinIO console (http://localhost:9001) → `thumbnails` bucket → real images, viewable.
- Re-running the exact same command: counts unchanged (not doubled), `updated_at` bumps on affected rows, `created_at` stays fixed from the first run.

## What to look out for

- **Live verification is still pending in this environment.** `.env`'s `YOUTUBE_API_KEY` has been blank throughout Stages 2, 3, and 5 - everything that doesn't need it (Stage 1's schema/migration, Stage 4's thumbnail pipeline, all unit tests, and 2 integration tests against your live dev Postgres) has been run and verified for real. Everything that does need it (`inspect-channel`, `inspect-video`, and the real `slop ingest channel`) has only been verified at the code level - lint, unit tests, and the "missing key fails cleanly" path. **The roadmap's actual Phase 1 checkpoint - ingesting 3–5 real channels and eyeballing the data - is the one piece you still need to do yourself**, once a key is in `.env`.
- **A real naming inconsistency was found and kept as-approved**: thumbnails are always stored under the key `{video_id}.jpg`, but yt-dlp sometimes hands back a WebP image as the best available thumbnail (confirmed live against a real video during Stage 4 testing). The stored `content_type` is correct either way, so nothing is functionally broken, but a `.jpg` key can contain WebP bytes. This was surfaced and you didn't ask for a change, so it's in the real pipeline now (Stage 5). Still fixable if you'd rather the extension match the real format - say so and it's a small, contained change.
- **A deliberate refinement beyond the written plan**: a thumbnail failure for one video does not discard that video's already-fetched metadata and comments - only the thumbnail row is skipped for that video (and recorded in the run's "issues" list). Only a comments-fetch or DB-write failure discards the whole video.
- **Transaction granularity**: each video's row + all its comments + its thumbnail row commit together in one transaction, after that video's network calls have already completed - a mid-run crash loses at most the one video that was in flight, not the whole channel.
- **Quota cost** for a full channel ingest is roughly 1 unit per video (plus a small constant for channel/playlist/batch lookups) - cheap against the 10k/day budget, but worth knowing before running against several channels back-to-back.
- The ORM models live in `src/sloppy/db/`, not `src/sloppy/models/` - that name is reserved for the Phase 3–4 ML models.
- `google-api-python-client` (not raw HTTP) is the YouTube client, per an explicit decision made before Stage 2 - trades static typing for less boilerplate; all real validation happens through the pydantic `ChannelMeta`/`VideoMeta`/`CommentMeta` models.

## How to run tests properly

```powershell
# 1. Bring up the dev stack (both Postgres and MinIO are needed for the full suite)
docker compose up -d

# 2. Full automated test suite - 19 tests as of the end of Phase 1, including 2 that hit
#    the live dev Postgres directly to prove upsert idempotency
uv run pytest -v

# 3. Lint
uv run ruff check .

# 4. Migration state sanity check
uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d channels" -c "\d videos" -c "\d comments" -c "\d thumbnails"

# 5. CLI wiring sanity check (no API key needed)
uv run slop --help
uv run slop ingest --help
uv run slop smoke

# 6. Thumbnail pipeline, live (no API key needed - yt-dlp reads the public watch page directly)
uv run slop ingest inspect-thumbnail <any real video id>
# check http://localhost:9001 → thumbnails bucket

# 7. THE remaining step - full live verification (REQUIRES a real YOUTUBE_API_KEY in .env):
uv run slop ingest channel <a real @handle, start small>
docker compose exec postgres psql -U slop -d slopornot \
  -c "SELECT count(*) FROM channels;" -c "SELECT count(*) FROM videos;" \
  -c "SELECT count(*) FROM comments;" -c "SELECT count(*) FROM thumbnails;"
docker compose exec postgres psql -U slop -d slopornot \
  -c "SELECT id, title, duration_seconds, topic_categories FROM videos LIMIT 10;"

# idempotency check - re-run the same command, re-run the count queries, counts must match:
uv run slop ingest channel <the same handle>

# repeat against 2-4 more channels to reach the roadmap's "3-5 channels, ~200+ videos" bar
```

## What's next

Phase 1's code is complete; the only open item is your own live verification once `YOUTUBE_API_KEY` is set, plus a decision on the thumbnail-extension naming question above. After that, Phase 2 (Rubric & labeling) is next per `ROADMAP.md` - a written definition of "slop," a `labels` table, and a keyboard-driven labeling CLI.
