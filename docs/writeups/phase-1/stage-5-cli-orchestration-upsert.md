# Phase 1, Stage 5 - CLI orchestration + idempotent upsert wiring

## What is being implemented

The final piece of Phase 1: wiring Stages 1–4 together into one real command, `slop ingest channel <id|handle>`, and making it idempotent (safe to re-run on the same channel without duplicating rows).

New files:
- `src/sloppy/ingest/upsert.py` - `upsert_channel`, `upsert_video`, `upsert_comment`, `upsert_thumbnail`, each using `postgresql.insert(...).on_conflict_do_update(...)`. Every table's PK is YouTube's own id (or `video_id` for `thumbnails`), so a re-run is always an update-in-place, never a duplicate row.
- `src/sloppy/ingest/pipeline.py` - `ingest_channel(settings, id_or_handle) -> IngestSummary`: resolves the channel, upserts it, lists all uploaded video ids, fetches+upserts video metadata in batches of 50, and for each video fetches comments + extracts/downloads/uploads its thumbnail, upserting all of it together.
- `tests/test_upsert.py` - integration tests against the real dev Postgres proving upserts don't duplicate rows on a second run.
- CLI: real `slop ingest channel <id|handle>` command in `src/sloppy/cli.py`, alongside the `inspect-*` debug commands from Stages 2–4.

Minor cleanup: removed the empty `@app.callback()` workaround noted in `DEVIATIONS.md` - it was only needed when `smoke` was the CLI's only command; now that `ingest` exists as a second top-level command, Typer doesn't collapse into single-command mode, so the workaround is gone. Verified `slop --help` and `slop smoke` still work identically afterward.

## A deliberate refinement beyond the literal plan text

The plan said "each video's work wrapped in try/except ... logs a warning and continues." I implemented something slightly more careful: **a thumbnail failure alone does not discard that video's metadata and comments.** Comments and thumbnail extraction/upload happen first (outside any DB transaction); if the thumbnail step throws, the video and its comments are still upserted in the one commit for that video, and only the thumbnail row is skipped (recorded as an issue in the summary, not silently dropped). Only a failure in fetching comments, or in the DB write itself, discards the whole video. This avoids wasting good data over what will sometimes be a transient/edge-case thumbnail problem (e.g. a livestream with no static thumbnail, an occasional yt-dlp extraction quirk).

## What it should look like

```
$ uv run slop ingest channel @somechannel
Ingested channel UCxxxxxxxxxxxxxxxxxxxxxx
  videos upserted:     47
  comments upserted:   3210
  thumbnails upserted: 46

1 issue(s):
  - abc123XYZ00: thumbnail failed: No thumbnail with known dimensions available
```

Re-running the exact same command immediately after should print the same or very similar counts (comments could shift slightly if new ones were posted in between) - never doubled - and the "issue(s)" section, if present, tends to be small and about specific edge-case videos, not systemic.

## What to look out for

- **Not yet run against real data in this environment** - `YOUTUBE_API_KEY` in `.env` is still blank, so `slop ingest channel` itself hasn't been exercised live here (same blocker as Stages 2–3). Everything else has been verified: 19/19 tests pass (including 2 new integration tests that actually hit the live dev Postgres - they'd fail loudly if the DB were unreachable, and the pass count went from 17 to 19 confirming they ran), lint is clean, and `slop --help`/`slop smoke` still work after removing the callback workaround.
- **Transaction granularity**: each video's video-row + all its comments + its thumbnail row commit together, in one transaction, after that video's network calls (comments fetch, thumbnail extract/download/upload) have already completed. This means a mid-run crash leaves every already-processed video durably in the DB - you'd only lose the one video that was in-flight, not the whole channel.
- **The channel's `last_ingested_at`** is set once, at the very end of the run, regardless of whether any individual videos failed. It marks "a full pass was attempted," not "every video succeeded."
- **This is where the Stage 4 `.jpg`/webp naming question actually lands in real data** - I proceeded with the plan's flat `{video_id}.jpg` key scheme since you didn't flag a change; happy to revisit if it bothers you once you see it across ~200 real rows.
- Quota cost for a full channel ingest: roughly `1 (channel) + ceil(videos/50) (playlist pages) + ceil(videos/50) (video metadata batches) + videos (comment threads, ~1 each) ` units. For a channel with ~200 videos that's roughly 210 units - cheap against the 10k/day budget, but worth being aware of before running this against many channels in one sitting.

## How to run tests properly

```powershell
# 1. Make sure Postgres/MinIO are up (test_upsert.py needs a live DB)
docker compose up -d

# 2. Full suite - 19 tests total after this stage, including 2 live-DB idempotency tests
uv run pytest -v

# 3. Lint
uv run ruff check .

# 4. Confirm the CLI still works correctly without the removed callback
uv run slop --help
uv run slop smoke

# 5. Live end-to-end verification (REQUIRES a real YOUTUBE_API_KEY in .env - not yet configured here)
#    This is the roadmap's actual Phase 1 checkpoint.
uv run slop ingest channel <a real @handle, ideally a smaller channel first>

# then, via psql or a GUI client:
docker compose exec postgres psql -U slop -d slopornot -c "SELECT count(*) FROM channels;" \
  -c "SELECT count(*) FROM videos;" -c "SELECT count(*) FROM comments;" -c "SELECT count(*) FROM thumbnails;"
docker compose exec postgres psql -U slop -d slopornot -c \
  "SELECT id, title, duration_seconds, topic_categories FROM videos LIMIT 10;"

# open http://localhost:9001 and browse the thumbnails bucket

# 6. THE idempotency check - re-run the exact same command and re-run the count queries.
uv run slop ingest channel <the same handle>
# counts must be unchanged (not doubled); updated_at should bump on affected rows while
# created_at stays fixed from the first run:
docker compose exec postgres psql -U slop -d slopornot -c \
  "SELECT id, created_at, updated_at FROM videos ORDER BY updated_at DESC LIMIT 5;"

# 7. Repeat step 5 against 2-4 more real channels (~200+ videos total) to match the
#    roadmap's Phase 1 verification bar of "ingest 3-5 channels, row counts sane."
```
