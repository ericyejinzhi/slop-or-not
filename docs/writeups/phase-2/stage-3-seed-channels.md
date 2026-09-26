# Phase 2, Stage 3 - Seed-channel bulk ingestion + status

## What is being implemented

Tooling around `data/seed_channels.csv`, the hand-curated list of 40-80 channels the roadmap calls for. Curating the actual list (real channel research, genre balance, "boring mid-tier" inclusion) is your judgment call, not automatable - this stage just makes it cheap to act on that list once it exists.

- `slop ingest seed-channels` - reads the CSV, calls Phase 1's existing `ingest_channel()` per row unchanged, tolerates per-channel failures (one bad row doesn't abort the rest), exits 1 only if every row failed.
- `slop label seed-status` - cross-references the CSV against the `channels` table, reporting ingested/missing and flagging any channel under the roadmap's 15-video floor.
- New `label_app` Typer sub-app (`slop label ...`), mounted alongside the existing `ingest_app`.

## What it should look like

Once you've filled in some real rows in `data/seed_channels.csv`:

```
$ uv run slop ingest seed-channels
[ok] @somechannel: 47 videos, 3210 comments, 46 thumbnails
[ok] @anotherchannel: 22 videos, 1500 comments, 22 thumbnails
[FAIL] @typoedhandle: No YouTube channel found for '@typoedhandle'

2 channel(s) ingested, 1 failed

$ uv run slop label seed-status
[ok]      @somechannel: 47 videos
[ok]      @anotherchannel: 22 videos
[missing] @typoedhandle: not ingested
```

## What to look out for

- **Verified against the empty CSV and a fake handle, not real data yet.** `data/seed_channels.csv` is still header-only in this environment (you haven't curated your channel list yet) and `YOUTUBE_API_KEY` is still blank, so `seed-channels` itself couldn't be run against real YouTube data. What I did verify directly: `seed-status` against the empty CSV prints "No rows found" and exits 1; against a CSV with one fake handle it correctly prints `[missing] ... not ingested`; `seed-channels` correctly refuses to run without an API key.
- Handle matching is normalized (`.lstrip("@").lower()`) on both sides before comparing your CSV's `handle` column against the DB's `channels.handle` - YouTube's API returns handles with a leading `@`, and this avoids a silent case/`@`-prefix mismatch making `seed-status` wrongly report a real, ingested channel as missing.
- `seed-channels` catches broad `Exception`, not just the `ValueError` that `resolve_channel` raises for an unknown handle - this matches Phase 1's own philosophy (one bad item shouldn't abort a multi-item run), but means a genuine bug elsewhere in the ingest pipeline would also just get logged as a per-channel failure here rather than crashing loudly. Worth keeping an eye on the failure messages the first few times you run this against your real list.
- `ingest_channel()` itself is completely unchanged from Phase 1 - this stage only adds a loop around it.

## How to run tests properly

```powershell
# 1. Full suite
uv run pytest

# 2. Lint
uv run ruff check .

# 3. CLI wiring sanity check (no data or API key needed)
uv run slop label --help
uv run slop label seed-status   # should print "No rows found" against the still-empty CSV

# 4. Once you've filled in a few real rows in data/seed_channels.csv AND set YOUTUBE_API_KEY:
uv run slop ingest seed-channels
uv run slop label seed-status
# cross-check against:
docker compose exec postgres psql -U slop -d slopornot -c "select channel_id, count(*) from videos group by 1;"
```
