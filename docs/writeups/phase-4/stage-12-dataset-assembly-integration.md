# Phase 4, Stage 12 - Dataset assembly integration

## What is being implemented

The integration point wiring everything Stages 2-11 built into one training-ready DataFrame: `assemble_dataset` now, per labeled video, (1) computes metadata features as before, (2) left-joins `VideoNlpFeatures`, (3) left-joins `VideoVisionFeatures`, (4) computes the 3 cross-video similarity queries, (5) rolls up channel-level sentiment, (6) computes the 3 feature interactions using columns from steps 1-5. `train.py`'s `NUMERIC_FEATURES`/`CATEGORICAL_FEATURES` grew from 15/2 to 34/3 columns to include everything - scalar NLP/vision/similarity/interaction features, never raw embeddings (per the earlier decision that raw 384/512-dim vectors would overfit badly at this label scale).

## What it should look like

```python
>>> df = assemble_dataset(session, splits)
>>> df.columns.tolist()
['video_id', 'channel_id', ..., 'sentiment_mean', ..., 'clip_clickbait_score', ...,
 'channel_thumbnail_self_similarity', ..., 'lure_score_x_genre', 'y', 'split']
```

A video not yet processed by `slop features compute-nlp`/`compute-vision` still gets a row - every NLP/vision/interaction column for it is `NaN` (numeric) or missing (categorical), never a crash.

## Two rounds of expected fixture-maintenance regressions, plus one real test-correctness bug

- **Expected, same pattern as Stage 2**: growing `NUMERIC_FEATURES`/`CATEGORICAL_FEATURES` broke `test_model_train.py`'s synthetic `_separable_dataframe()` fixture again (now missing ~20 more required columns). Fixed by extending the fixture with neutral constant values for every new column, same as before.
- **A genuine test-writing mistake, not a code bug**: my first version of the new Stage 12 integration test asserted `row1["sentiment_mean"] is None` for a video with no NLP features processed. This failed with `assert np.float64(nan) is None` - not because `assemble_dataset` did anything wrong, but because pandas coerces a column that mixes `None` and real float values into a `float64` column using `NaN` as the missing marker, not Python's `None` object. The same thing happened for the *categorical* `lure_score_x_genre` column too (also became `NaN`, not `None`, once mixed with a real string value in the same object column). Fixed both assertions to use `pd.isna(...)`, the actually-correct way to check for "missing" in a DataFrame regardless of column dtype.

## What to look out for

- **Corpus stats and the channel sentiment rollup are both built from ALL ingested/processed videos, not just the labeled subset** - verified directly: a test channel has 2 videos, only one processed through NLP/vision features, both labeled; the processed video's real sentiment/CLIP/interaction values come through exactly as inserted, and the unprocessed video's equivalents are all correctly missing rather than defaulting to some fake "neutral" value.
- `lure_score_x_genre`'s "high"/"low" split was verified against a real row: a video with `title_lure_score=0.8` (above the 0.5 threshold) produced `"{genre}::high"` exactly as `interactions.py`'s logic specifies.
- This stage doesn't introduce any new ML - it's pure plumbing/joining. The genuine "does this actually help" question is now fully deferred to Stage 13 (ablation) plus real labeled data.

## How to run tests properly

```powershell
docker compose up -d
uv run pytest tests/test_features_dataset.py tests/test_model_train.py -v
uv run pytest    # full suite - 120 passed, 5 deselected
uv run ruff check .
```
