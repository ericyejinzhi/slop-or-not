# Phase 2 - Rubric & labeling (full write-up)

This covers the whole of Phase 2 end-to-end. For stage-by-stage detail, see `stage-1-rubric.md` through `stage-7-consistency-and-stats.md` in this same directory.

## What is being implemented

Everything needed to turn Phase 1's raw ingested corpus into a labeled training set: a written definition of "slop" (`docs/rubric.md`), a `labels` table, tooling to bulk-ingest a hand-curated channel list, a pool-selection mechanism enforcing the roadmap's corpus-shape rules, a keyboard-driven labeling CLI, and a channel-grouped stratified train/val/test split.

Built across seven stages:

1. **`docs/rubric.md`** - the written definition of slop (four signal categories, edge cases, worked examples, the `up`/`down`/`skip` protocol).
2. **`labels` table** (`src/sloppy/db/models.py`, a migration) - event-log schema (not unique on `video_id`, since relabeling is intentional), plus a `labeler_name` setting.
3. **Seed-channel tooling** (`slop ingest seed-channels`, `slop label seed-status`) - bulk-ingests your curated `data/seed_channels.csv` via Phase 1's existing pipeline, and cross-checks it against what's actually in the DB.
4. **Pool selection** (`src/sloppy/label/pool.py`, `slop label pool-preview`) - enforces "recent uploads only, >=15/<=30 per channel, wide-and-shallow" at query time.
5. **The labeling CLI** (`src/sloppy/label/keyboard.py`, `display.py`, `labels.py`, `slop label run`) - the actual keyboard-driven tool.
6. **Train/val/test split** (`src/sloppy/label/split.py`, `slop label make-splits`) - channel-grouped, dependency-free, writes `data/splits.csv`.
7. **Distribution + consistency tooling** (`slop label stats`, `--mode consistency`) - closes out the roadmap's own verify bullet.

## Architecture, end to end

```
docs/rubric.md  (your judgment, codified)
        |
data/seed_channels.csv  --[slop ingest seed-channels]--> Phase 1's ingest_channel() (unchanged)
        |                                                        |
        |                                                        v
        |                                          channels / videos / comments / thumbnails
        |                                                        |
        `--[slop label seed-status]-----------------------------'
                                                                  |
                                          candidate_videos() + sample_pool()   (pool.py)
                                                                  |
                                                    slop label run  (keyboard.py, display.py)
                                                                  |
                                                                  v
                                                             labels table
                                                                  |
                          slop label stats <--- agreement/distribution checks
                                                                  |
                          slop label make-splits ---> data/splits.csv  (split.py)
```

Every table added or touched in Phase 2 still follows Phase 1's conventions: `Base`/`TimestampMixin`, no ORM `relationship()` (manual joins/lookups), `session_scope()` for all writes, SQLAlchemy 2.0-style typed models.

## What it should look like

Once you've curated `data/seed_channels.csv` and set `YOUTUBE_API_KEY` + `LABELER_NAME`:

```
$ uv run slop ingest seed-channels
[ok] @channel1: 25 videos, 1800 comments, 25 thumbnails
...

$ uv run slop label pool-preview
Candidates before exclusion: 1200  after excluding labeled: 1200  sampled pool: 400
...

$ uv run slop label run --limit 50
Labeling as 'eric'. 400 video(s) in this pool.
Keys: y=up (quality)   n=down (slop)   s=skip   q=quit
...

$ uv run slop label stats
Overall label counts:
  up: 210
  down: 90
  skip: 12
  minority-class share: 30.0%
...

$ uv run slop label make-splits
Wrote 300 labeled video(s) to data\splits.csv
  train: 210
  val: 45
  test: 45
```

## What to look out for

- **Two real algorithm bugs were found and fixed during implementation, not just theoretical risks:**
  1. `cache_thumbnail`'s extension-from-content-type logic (Stage 5) initially relied on stdlib `mimetypes.guess_extension`, which returns `None` for `"image/webp"` on this machine - silently reproducing the exact `.jpg`-labeled-WebP bug it was built to prevent. Fixed with an explicit content-type-to-extension map.
  2. The train/val/test split's greedy channel-assignment algorithm (Stage 6) went through two wrong cost-normalization schemes before landing on a correct one - the first two both mishandled bins with very different target sizes (70% vs 15% vs 15%), landing at 40% and then 0% train share respectively on a test corpus, instead of the intended 70%. Caught by writing proportion/balance assertions into the tests *before* trusting the implementation, then stress-testing with a more realistic uneven-channel synthetic corpus.
- **The interactive labeling loop (`slop label run`, both normal and `--mode consistency`) cannot be tested headlessly, and this was confirmed rather than assumed** - piping input into it hangs, because `readchar` reads the console device directly, not redirected stdin. Everything up to the keypress (pool selection, video display, thumbnail download, the "no thumbnail" warning path) was verified via real runs against real Postgres/MinIO before hitting that wall each time. **Actually pressing keys is the one thing in this phase that needs your own hands-on test.**
- **Nothing in this phase has been run against your real corpus yet** - `YOUTUBE_API_KEY` and `LABELER_NAME` are both still blank in `.env`, and `data/seed_channels.csv` is still header-only (real channel curation is explicitly your call, not automatable). Every piece that doesn't need those was verified directly against real Postgres/MinIO with synthetic data, then cleaned up; nothing synthetic was left behind.
- **`data/splits.csv` is gitignored on purpose** - it's fully reproducible from the `labels` table plus a fixed `--seed`, unlike the hand-curated `seed_channels.csv`.
- No `severity` column exists on `labels` - the roadmap explicitly defers that decision to after your first ~50 real labels.
- `labels.video_id` is intentionally not unique - relabeling adds a new row, which is what makes the Stage 7 consistency check possible at all.

## How to run tests properly

```powershell
# 1. Bring up the dev stack
docker compose up -d

# 2. Full automated suite - 37 tests as of the end of Phase 2, including several that
#    hit the live dev Postgres directly (pool selection, upserts, label recording,
#    consistency sampling)
uv run pytest -v

# 3. Lint
uv run ruff check .

# 4. Migration + schema sanity check
uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d labels"

# 5. CLI wiring sanity check (no API key or real data needed)
uv run slop label --help
uv run slop label pool-preview
uv run slop label stats

# 6. The pieces that need your own hands-on setup:
#    a. Fill in data/seed_channels.csv with real, researched channels (genre-paired,
#       including the "boring mid-tier" - see docs/rubric.md and ROADMAP.md's channel
#       selection rules)
#    b. Set YOUTUBE_API_KEY and LABELER_NAME in .env
#    c. uv run slop ingest seed-channels
#    d. uv run slop label pool-preview   (sanity-check corpus shape before labeling)
#    e. uv run slop label run --limit 50   (the actual labeling - keyboard-driven, in a
#       real terminal)
#    f. uv run slop label stats   (check the minority-class floor)
#    g. uv run slop label make-splits   (produces data/splits.csv for Phase 3)
#    h. A week later: uv run slop label run --mode consistency --limit 20, then
#       uv run slop label stats again to see the agreement rate
```

## What's next

Phase 2's code is complete. The remaining work is entirely yours: curate `data/seed_channels.csv`, get a YouTube API key if you haven't already, read through `docs/rubric.md` and adjust it to match your own judgment, then actually label. Once you have a real `data/splits.csv`, Phase 3 (Baseline model) is next per `ROADMAP.md` - metadata-only feature engineering, logistic regression + XGBoost, and a `video_scores` table.
