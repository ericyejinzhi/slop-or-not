# Phase 2, Stage 4 - Pool selection + preview CLI

## What is being implemented

The logic that turns "everything ingested" into "the specific 300-500 videos you should actually label," enforcing the roadmap's corpus-shape rules at selection time (since Phase 1 ingestion pulls a channel's entire history, not just its recent uploads).

- `candidate_videos(session, per_channel_max, exclude_labeled)` - a window-function query (`ROW_NUMBER() OVER (PARTITION BY channel_id ORDER BY published_at DESC)`) that takes each channel's N most recent videos, optionally excluding anything that already has a label row.
- `sample_pool(candidates, target_size, seed)` - a pure, seeded shuffle-and-truncate.
- `slop label pool-preview` - runs both without touching the `labels` table, printing before/after-exclusion counts, a per-channel breakdown (flagging any channel under 15 total ingested videos), and a per-genre breakdown (genre joined in from `seed_channels.csv`, not stored in the DB).

New package: `src/sloppy/label/` (`pool.py`).

## What it should look like

```
$ uv run slop label pool-preview
Candidates before exclusion: 850  after excluding labeled: 850  sampled pool: 400

Per-channel counts:
  @somechannel: 22
  @anotherchannel: 18
  ...

Per-genre counts:
  gaming: 140
  cooking: 95
  unknown: 40
  ...
```

Re-running with a different `--seed` should change which exact videos land in the sample but keep the per-channel/per-genre *proportions* roughly stable.

## What to look out for

- **Verified end-to-end against real Postgres, but with synthetic data** - the real corpus is still empty (no API key yet), so I inserted a temporary test channel/videos directly, confirmed `candidate_videos` correctly capped it at N-most-recent and excluded labeled videos, then deleted the test rows. Ran `pool-preview` against the real (currently empty) database too, confirming it prints clean zero counts rather than crashing.
- The per-channel-max cap uses `published_at`, so a channel that back-fills old uploads or has inconsistent publish dates could behave surprisingly - this hasn't come up yet since there's no real data, but worth a glance once you have some.
- Genre comes from `seed_channels.csv`, joined by normalized handle - a channel not found in the CSV (or with a blank `genre` cell) buckets into `"unknown"` rather than erroring.
- `exclude_labeled=True` checks for *any* label row (including `skip`) via `NOT EXISTS` - once you've looked at a video and hit skip, it won't reappear in a fresh `pool-preview`/`label run` pool. (Deliberately revisiting skipped or already-labeled videos is what `--mode consistency`, added in Stage 7, is for.)

## How to run tests properly

```powershell
# 1. Full suite - includes a live-Postgres integration test for candidate_videos
docker compose up -d
uv run pytest

# 2. Lint
uv run ruff check .

# 3. Live check against whatever's actually in your DB
uv run slop label pool-preview
uv run slop label pool-preview --seed 2   # compare - counts change, proportions shouldn't move much
```
