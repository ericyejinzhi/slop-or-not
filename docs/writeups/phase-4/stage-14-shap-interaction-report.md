# Phase 4, Stage 14 - SHAP interaction report (standalone script)

## What is being implemented

`scripts/shap_interaction_report.py` - a plain `argparse` script (not a `slop` CLI subcommand, not a package module under `src/sloppy`) that loads a trained model artifact, re-assembles the same evaluation dataset used for training/evaluation, and writes the top-N feature-interaction pairs (by mean absolute SHAP interaction value) to a CSV. This is the last stage of the 14-stage Phase 4 plan.

The pure extraction logic lives in `top_interaction_pairs(interaction_values, feature_names, n=20)`: given SHAP's raw per-sample interaction tensor (shape `(n_samples, n_features, n_features)`), it averages absolute interaction strength across samples, then returns the top-N `(feature_i, feature_j, mean_abs_interaction)` triples from the upper triangle only (the matrix is symmetric, and the diagonal holds each feature's own main effect, not an interaction).

`main()` wires this to the real world: `joblib.load(model_path)` for the pipeline, `metadata.json` (written by `save_model` in Stage 13) for the feature list, `assemble_dataset` + `load_splits` (Stage 12) for the evaluation rows, `pipeline.named_steps["preprocess"].transform(...)` to get the same matrix the estimator actually saw, `pipeline.named_steps["preprocess"].get_feature_names_out()` for post-one-hot-encoding column names (so the report says `genre_Gaming`, not just `genre`), and `shap.TreeExplainer(estimator).shap_interaction_values(...)` for the interaction tensor itself.

## What it should look like

Once a real "all features" model exists (deferred - no real labeled data yet), the intended usage is:

```
$ uv run python scripts/shap_interaction_report.py models_artifacts/xgboost/20260926-201233/model.joblib \
    --splits-csv data/splits.csv --split test --n 20
Wrote top 20 interaction pairs to docs/writeups/phase-4/shap-interactions.csv
```

producing a CSV like:

```
feature_i,feature_j,mean_abs_interaction
title_lure_score,clip_clickbait_score,0.0412
duration_deviation_channel,channel_upload_cadence_days,0.0288
...
```

This run against real data is explicitly **not** performed as part of this stage - same deferral as every other "does this feature actually help" question in Phase 4 (Stage 13's ablation table, Stage 10's similarity thresholds). There is no trained "all features" model yet because there is no real labeled data yet (see `docs/writeups/TODO.md`).

## What to look out for

- **`shap.TreeExplainer` requires a tree-based estimator.** It works for `xgboost` but will raise if pointed at a `logistic_regression` artifact - this is a real constraint of the tool, not a bug to work around; the script's docstring calls it out.
- **Feature names are post-preprocessing, not the raw column names.** `ColumnTransformer.get_feature_names_out()` renders one-hot columns as `categorical__genre_Gaming` (imputed numeric columns keep their original name, prefixed `numeric__`) - so a "genre x duration interaction" in the CSV will actually show up as several rows, one per genre category interacting with duration. This is unavoidable given how tree-based SHAP interaction values work (they operate on the model's actual input matrix, post-encoding) - worth remembering when reading the CSV so a single semantic interaction isn't mistaken for several independent ones.
- **`interaction_values` can come back as a list** (one array per class) depending on the shap/xgboost version and whether the estimator is binary or multi-class. The script normalizes this by taking the last element (the positive/"down" class) when a list is returned - this was written defensively based on shap's documented behavior for some estimator types, not confirmed against a real run yet (no trained model to test against), so treat it as a first-pass assumption to double check once Stage 14 is actually run for real.
- **This script is deliberately outside `src/sloppy`** and is not installed as part of the package - it won't be reachable via `slop ...` and isn't wired into `pyproject.toml`'s package list. This matches the plan's framing: a one-off analysis artifact for the README, not a routinely-run command like `slop model evaluate`.
- **Test import trick**: since `scripts/` has no `__init__.py` and isn't a package, `tests/test_shap_report.py` inserts `scripts/` onto `sys.path` directly before importing (`from shap_interaction_report import top_interaction_pairs`) rather than using a package-qualified import. This is standalone-script testing, not the pattern used anywhere else in this codebase - don't copy it for anything that should become a real package module.

## How to run tests properly

```powershell
uv run pytest tests/test_shap_report.py -v
uv run pytest    # full suite - 127 passed, 5 deselected
uv run ruff check .
uv run ruff format --check scripts/shap_interaction_report.py tests/test_shap_report.py
```

All 3 tests are pure and fast - synthetic 3D numpy arrays standing in for a real SHAP interaction tensor, with hand-computed expected rankings (including a deliberate "diagonal must be excluded" case and an "averages across samples correctly" case). No model loading, no database, no real SHAP call. Running `scripts/shap_interaction_report.py` for real requires a trained model artifact and a populated `data/splits.csv` - both blocked on real ingestion/labeling, tracked in `docs/writeups/TODO.md`.
