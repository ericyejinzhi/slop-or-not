# Phase 3, Stage 6 - Dataset assembly

## What is being implemented

`assemble_dataset` turns `data/splits.csv` + the ingested corpus into a single training-ready pandas `DataFrame`: one row per labeled video, with every `VideoFeatures` field plus `channel_id`/`label`/`y` (1 if `down` else 0)/`split`. Callers filter by split (`df[df.split == "train"]`) rather than getting three separate return values.

File: `src/sloppy/features/dataset.py`.

## What it should look like

```python
>>> from sloppy.features.dataset import load_splits, assemble_dataset
>>> splits = load_splits(Path("data/splits.csv"))
>>> with session_scope() as session:
...     df = assemble_dataset(session, splits)
>>> df.columns.tolist()
['video_id', 'channel_id', 'title_caps_ratio', ..., 'label', 'y', 'split']
>>> df[df.split == "train"].shape
(240, 17)
```

## What to look out for

- **Corpus stats (channel/genre duration norms, upload cadence) are built from ALL ingested videos, not just the labeled subset** - this is the one thing this stage exists to get right. Verified directly: a test ingests 4 synthetic videos into one channel but only labels 2 of them (writing just those 2 into a synthetic `splits.csv`); `assemble_dataset` correctly returns exactly 2 rows (only the labeled ones appear in the dataset) while `duration_deviation_channel` for those rows is computed against all 4 videos' durations, not just the 2 that made it into the final dataset.
- If a `video_id` appears in `splits.csv` but isn't actually in the `videos` table (shouldn't happen in practice since `make-splits` reads from the same DB, but could happen with a stale CSV), it's silently skipped rather than erroring - `assemble_dataset` only produces rows for videos it can actually find.
- Verified with synthetic DB fixtures (a `_cleanup()`-guarded integration test, same pattern as `test_upsert.py`) - real-world correctness (whether the actual genre distribution looks sensible, etc.) is deferred until real ingestion + labeling happens.

## How to run tests properly

```powershell
docker compose up -d
uv run pytest tests/test_features_dataset.py -v
uv run ruff check .
```
