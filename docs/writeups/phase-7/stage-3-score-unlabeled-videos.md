# Phase 7, Stage 3 - Score already-ingested, unlabeled videos with an existing model

## What is being implemented

The one genuinely missing capability that "ingest -> features -> score" as a daily refresh flow needs: nothing before this stage could apply an *already-trained* model to a newly-ingested video that has no label at all. `slop model train` always fits a fresh model over `data/splits.csv`, and `assemble_dataset` requires every video to have a `(channel_id, label, split)` entry - there was no path from "a video was just ingested" to "a score exists for it" without a label ever entering the picture, which is exactly the realistic shape of production scoring (training happens occasionally over labeled data; scoring happens continuously over whatever was just ingested).

Two changes make this possible:

1. **`src/sloppy/features/dataset.py` refactored**, not rewritten - `assemble_dataset`'s per-video feature assembly (metadata + NLP/vision joins + similarity + interactions) was extracted into a shared `_build_video_record`/`_corpus_context` pair. A new `assemble_features_for_video_ids(session, video_ids) -> pd.DataFrame` calls the same shared logic for an arbitrary list of video ids, with no `label`/`y`/`split` columns attached - `score_dataframe`-style scoring only ever needed the feature columns, never the label, so this was a clean extraction rather than a new feature-engineering effort.
2. **New `src/sloppy/models/scoring.py::score_videos(video_ids, model_name, model_version, artifacts_dir, split="live") -> list[str]`** - loads a previously-saved `model.joblib`/`metadata.json` pair (the same format `save_model` produces), calls `assemble_features_for_video_ids`, scores with the loaded pipeline directly (`predict_proba` + the same `down_index = list(pipeline.classes_).index(1)` lookup `score_dataframe` uses), and upserts into `video_scores` with `split="live"` by default - a new split value, freely allowed since `VideoScore.split` has no `CHECK` constraint, distinguishing production-scored videos from `train`/`val`/`test` rows.

## What it should look like

```python
>>> score_videos(
...     video_ids=["abc123", "def456"],
...     model_name="xgboost",
...     model_version="20260101-000000",
...     artifacts_dir=Path("models_artifacts"),
... )
["abc123", "def456"]
```

```sql
SELECT video_id, model_name, model_version, score, predicted_label, split FROM video_scores WHERE split = 'live';
--  abc123 | xgboost | 20260101-000000 | 0.73 | down | live
```

Verified with 2 new tests in `tests/test_model_scoring.py` (a real `logistic_regression` trained on a tiny synthetic metadata-only dataset, saved via the real `save_model`, then loaded back and scored via `score_videos` against a real, separately-inserted Postgres video - confirming a `video_scores` row lands with `split="live"` and a valid probability/label) and 1 new test extending `tests/test_features_dataset.py` (`assemble_features_for_video_ids` produces the right columns, no label/y/split, and silently skips a nonexistent video id).

## What to look out for

- **A real bug caught by the first test run, not a test-writing mistake**: the test originally saved the trained model under an arbitrary label (`TEST_MODEL_NAME = "test_scoring_model"`) and then asked `score_videos` to load a model under that same name - but `save_model` (Phase 3) persists artifacts under `artifacts_dir / trained.name / trained.version`, where `trained.name` is whatever string was passed to `train_model(name, ...)` (`"logistic_regression"` in this case), not an independently choosable label. `joblib.load` failed with `FileNotFoundError` looking in the wrong directory. This wasn't a bug in `score_videos` - it correctly builds the same path `save_model` uses - it was the test assuming `model_name` could be anything, when really it's a real contract: **whatever name you pass to `train_model`/`save_model` is exactly the name you must pass to `score_videos` to load it back.** Fixed by aligning the test's constant with `trained.name`. Worth remembering for the Prefect flow (a later stage) and for `docs/writeups/TODO.md`'s active-model-promotion step: `ACTIVE_MODEL_NAME` must be the literal string passed to `slop model train --model <name>`, not a display label.
- **`assemble_features_for_video_ids` reuses the exact same `_corpus_context` (all-videos corpus stats, NLP/vision lookups, channel sentiment rollup) as `assemble_dataset`** - meaning scoring even a single newly-ingested video re-queries and rebuilds corpus-wide stats from scratch. This is correct (a video's `duration_deviation_channel` etc. genuinely depend on the whole corpus, not just itself) but means `score_videos` is not cheap to call one video at a time in a loop - the Prefect flow (a later stage) should batch all of a channel's newly-ingested video ids into one `score_videos` call, not call it per video.
- **The refactor of `dataset.py` was verified behavior-preserving, not assumed**: all of `assemble_dataset`'s existing tests (`test_features_dataset.py`, `test_model_train.py`) were re-run unmodified against the refactored code and all passed, confirming the extraction didn't change what `assemble_dataset` itself produces.
- `score_videos` silently drops a `video_id` with no matching `Video` row (via `assemble_features_for_video_ids`'s own graceful handling) rather than raising - consistent with `assemble_dataset`'s existing behavior for a `splits.csv` entry with no matching video, and appropriate for a flow that might be asked to score a video id that failed to ingest.

## How to run tests properly

```powershell
uv run pytest tests/test_features_dataset.py tests/test_model_scoring.py -v
uv run pytest    # full suite - 166 passed, 5 deselected
uv run ruff check .
uv run ruff format --check .
```

All tests hit the real dev Postgres (`docker compose up -d` required); `score_videos`' tests train a real (if trivial) scikit-learn pipeline and save/load it via the real filesystem (`tmp_path`), exercising the actual joblib artifact format rather than mocking it.
