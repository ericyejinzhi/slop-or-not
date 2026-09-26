# Phase 2, Stage 7 - Distribution + consistency-check tooling

## What is being implemented

The tooling that closes out Phase 2's roadmap "Verify" bullet directly: *"label distribution isn't degenerate (aim >=25% minority class); spot-check consistency by relabeling 20 videos a week later."*

- `consistency_sample(session, n, seed)` - randomly samples `n` videos that already have a non-skip label (added to `src/sloppy/label/pool.py`).
- `slop label run --mode consistency` - uses `consistency_sample` instead of the fresh-videos pool, so you can deliberately relabel a past sample.
- `slop label stats` - overall up/down/skip counts, minority-class share (flagged if under 25%), per-channel counts, and an agreement rate for any video that's been labeled more than once (same label both times vs. disagreement).

## What it should look like

```
$ uv run slop label stats
Overall label counts:
  up: 9
  down: 3
  skip: 0
  minority-class share: 25.0%

Per-channel counts:
  UC_somechannelid: up=9 down=3 skip=0

Consistency check: 2 video(s) relabeled, 1/2 agree (50.0%)
```

If the minority share drops under 25%, that line turns red with a `[WARN: below the 25% floor]` note - directly matching the roadmap's own quality bar.

## What to look out for

- **The `stats` output above is real, not illustrative** - I inserted synthetic labels (9 up, 3 down, deliberately at the 25% boundary; one video relabeled with disagreement, one with agreement) and ran the actual command against real Postgres. It correctly reported 25.0% (right at the floor, not flagged, since the check is strictly "< 25%"), and correctly found 1/2 agreement on the two relabeled videos.
- **`--mode consistency` was also exercised for real**, and this is where I hit the same headless-testing wall as Stage 5: I piped `"q"` into `slop label run --mode consistency` to test it non-interactively, and it hung the same way, for the same reason - `readchar` reads the console directly, not piped stdin. Before I had to stop the process, the output confirmed it correctly built the consistency-mode pool, selected a labeled video, and reached the same keypress prompt as the normal pool mode. Actually pressing keys in `--mode consistency` still needs your own hands-on test.
- `consistency_sample` only returns videos with at least one **non-skip** label - a video you've only ever skipped has nothing to be "consistent" with yet, so it's excluded (verified directly with a live-Postgres test: a video with an `up` label, one with only a `skip` label, and one with no label at all - only the `up`-labeled one came back).
- The agreement calculation only looks at videos with 2+ non-skip labels - it will report "no videos have been relabeled yet" until you actually run a consistency-mode session.

## How to run tests properly

```powershell
# 1. Full suite - includes a live-Postgres integration test for consistency_sample
docker compose up -d
uv run pytest

# 2. Lint
uv run ruff check .

# 3. After a normal labeling session:
uv run slop label stats
# should show real counts; if you want to see the degenerate-class warning fire,
# temporarily label a heavily skewed batch and re-run

# 4. A week into labeling, per the roadmap's own verify step:
uv run slop label run --mode consistency --limit 20
uv run slop label stats
# the "Consistency check" line should now reflect however many of those 20 agreed
# with your original judgment
```
