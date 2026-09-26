# Phase 4, Stage 11 - Feature interactions

## What is being implemented

The 3 explicit feature crosses the roadmap names: `lure_score x genre`, `duration_deviation x cadence`, `mysterious_score x duration_bucket`. XGBoost learns interactions natively (a key reason it's the fusion model), but seeding it with explicit crosses where the story is already known helps. Pure functions, no ML - `src/sloppy/features/interactions.py`.

## What it should look like

```python
>>> from sloppy.features.interactions import lure_score_x_genre, mysterious_score_x_duration_bucket
>>> lure_score_x_genre(0.8, "Gaming")
'Gaming::high'
>>> mysterious_score_x_duration_bucket(0.5, "long")
1.0
```

## What to look out for

- **`lure_score_x_genre` produces a categorical string, not a number** - genre has no natural order, so this cross is a concatenation (`"Gaming::high"`/`"Gaming::low"`) meant to flow through the existing `OneHotEncoder` pipeline as a new categorical feature, not a numeric one. `duration_deviation_x_cadence` and `mysterious_score_x_duration_bucket` are both plain numeric products, since `duration_bucket` (unlike genre) genuinely is ordinal (short < mid < long), which is why it gets `DURATION_BUCKET_ORDINAL` mapped to 0/1/2 rather than one-hot-encoded in this cross.
- All 3 functions propagate `None` rather than raising or silently defaulting to 0 when an input is missing - a video whose title-intent score or duration deviation hasn't been computed yet correctly produces a missing interaction feature, which `SimpleImputer`/`OneHotEncoder(handle_unknown="ignore")` already handle downstream without new preprocessing code.
- The `LURE_HIGH_THRESHOLD = 0.5` boundary is inclusive (`>=`), verified directly with a test at exactly 0.5.
- Fully and permanently testable without real data or a real model - every test uses hand-picked numbers with exactly predictable results.
- Not yet wired into `assemble_dataset`/`NUMERIC_FEATURES`/`CATEGORICAL_FEATURES` - that's Stage 12, since these crosses need columns from both the metadata `VideoFeatures` and the `VideoNlpFeatures` table, which only Stage 12's dataset assembly sees together.

## How to run tests properly

```powershell
uv run pytest tests/test_features_interactions.py -v
uv run pytest    # full suite
uv run ruff check .
```
