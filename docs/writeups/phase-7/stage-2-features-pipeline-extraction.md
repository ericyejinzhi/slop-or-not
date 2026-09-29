# Phase 7, Stage 2 - Extract compute-nlp/compute-vision into importable functions

## What is being implemented

`src/sloppy/cli.py`'s `compute-nlp`/`compute-vision` commands (Phase 4) had their entire logic written directly inside the Typer command bodies - fine for a CLI-only project, but Phase 7's Prefect tasks need to call the same logic without duplicating it or shelling out to `slop features compute-nlp` as a subprocess (which would be slow, hard to retry cleanly at the task level, and inconsistent with how Phase 5's API calls `ingest_channel`/`record_label` directly).

New `src/sloppy/features/pipeline.py`: `compute_nlp_features(video_id=None, limit=None, channel_id=None, only_missing=False) -> list[tuple[str, int]]` and `compute_vision_features(settings, video_id=None, limit=None, channel_id=None, only_missing=False) -> list[str]` - the exact logic moved verbatim out of the CLI commands, plus two new filters neither command had before:
- `channel_id` - scope to one channel's videos (needed for a per-channel Prefect flow).
- `only_missing` - skip videos that already have a features row, so a daily orchestrated refresh reprocesses only what's new instead of re-embedding a channel's entire history every single run.

`compute-nlp`/`compute-vision` in `cli.py` now just call these functions and print the same messages as before - `--channel-id`/`--only-missing` options were also added to both CLI commands for consistency (a human running them manually gets the same new capabilities the Prefect flow will use).

## What it should look like

```
$ slop features compute-nlp --channel-id UC_x --only-missing
  video_123: 4 comment(s) scored
Computed NLP features for 1 video(s).

$ slop features compute-nlp --channel-id UC_x --only-missing
No matching videos found.
```

(second run finds nothing left to do, since the one video that needed processing already got it)

Verified with 5 new tests in `tests/test_features_pipeline.py`, real Postgres integration with sentiment/embedding/title-intent/CLIP calls all monkeypatched to canned values (fast, no network): `compute_nlp_features` processes matching videos and persists exactly the expected values; `video_id` filters to one video; `only_missing` correctly skips an already-processed video on a second call; `compute_vision_features` only picks up videos with a thumbnail on record; its own `only_missing` filter behaves the same way.

## What to look out for

- **A real cleanup-ordering bug found while writing this stage's tests, not in the application code**: the first version of `_cleanup()` in the new test file deleted `Video` rows before `Comment` rows, and Postgres correctly rejected it with `ForeignKeyViolation: update or delete on table "videos" ... still referenced from table "comments"`. Fixed by deleting `Comment` rows first - a reminder that this project's FK-ordered cleanup pattern (children before parents) has to be gotten right every time a new test touches a table with dependents, not just copy-pasted from a similar-looking prior test that happened not to need it.
- **`only_missing` uses a `LEFT JOIN ... WHERE features_table.video_id IS NULL`**, the standard SQL idiom for "rows in A without a matching row in B" - not a subquery or an `EXISTS`/`NOT EXISTS` check like `candidate_videos`' `exclude_labeled` filter (Phase 2) uses. Both achieve the same logical result; this one was chosen since it composes cleanly with the existing `query.filter(...)` chain already being built up for `video_id`/`channel_id`.
- **The CLI's behavior is unchanged for anyone not passing the two new flags** - `--channel-id`/`--only-missing` both default to their prior implicit behavior (`None`/`False`), so `slop features compute-nlp` with no arguments does exactly what it always did. This refactor was verified to be behavior-preserving by re-running the full test suite (163 passed) rather than assumed.
- `compute_vision_features` takes `settings: Settings` as an explicit first argument (needed to build the S3 client), while `compute_nlp_features` needs no settings at all (sentiment/embedding models don't need any project config) - this asymmetry is intentional, not an oversight, and mirrors the underlying functions' own real dependencies rather than forcing a uniform signature for its own sake.

## How to run tests properly

```powershell
uv run pytest tests/test_features_pipeline.py -v
uv run pytest    # full suite - 163 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .
```

All 5 tests hit the real dev Postgres (`docker compose up -d` required) via the standard `_cleanup()`-guarded, real-upsert-helper pattern - only the ML model calls are monkeypatched, not the database layer.
