# Phase 3, Stage 7 - Model training (logistic regression + XGBoost) + CLI

## What is being implemented

The actual baseline models: `slop model train --model logistic_regression|xgboost|both` assembles the dataset (Stage 6), fits a scikit-learn `Pipeline` (median-impute + passthrough numeric features, one-hot encode `duration_bucket`/`genre`) around either `LogisticRegression(class_weight="balanced")` or `XGBClassifier` (both CPU-only, no GPU config anywhere), persists the artifact to `models_artifacts/<name>/<version>/` (`model.joblib` + `metadata.json`), scores every labeled video, and upserts the results into `video_scores` (Stage 5).

- `src/sloppy/models/train.py` - `build_preprocessor`, `train_model`, `save_model`, `score_dataframe`.
- `src/sloppy/models/tracking.py` - best-effort W&B wrapper per your confirmed decision: `start_run` returns `None` (no-op) if `WANDB_API_KEY` is unset, or if `wandb.init()` raises for any reason - training never fails because of W&B.
- `src/sloppy/cli.py` - new `model_app`, command `train`.

## What it should look like

```
$ uv run slop model train --model both
Training logistic_regression on 240 row(s)...
  saved to models_artifacts\logistic_regression\20260926-005117\model.joblib
  scored 342 video(s), version=20260926-005117
Training xgboost on 240 row(s)...
  saved to models_artifacts\xgboost\20260926-005119\model.joblib
  scored 342 video(s), version=20260926-005119
```

## This was actually run end-to-end against real Postgres + MinIO - real result, not illustrative

Since no real labeled data exists yet, I built a small synthetic corpus (8 channels x 10 videos, with duration deliberately correlated with the label - short/clickbait-titled videos coded "down," long documentary-titled videos coded "up") and ran the real `slop model train --model both` command against it through the real CLI, real database, real trained scikit-learn/XGBoost models. Both models correctly separated the classes:

```
                     | avg score, label=down | avg score, label=up
logistic_regression  |         0.99999...    |      0.0000015
xgboost              |         0.967         |      0.033
```

This validates the entire pipeline end-to-end - training, artifact persistence (`metadata.json` correctly recorded `sklearn_version: "1.9.1"`, `xgboost_version: "3.4.1"`, `train_row_count: 60`), and scoring/upserting into `video_scores`. **What this does NOT and cannot validate is real predictive power on actual YouTube slop** - the synthetic signal was deliberately made perfectly learnable; whether logistic regression/XGBoost meaningfully beat the majority baseline on real, messy, human-labeled data is exactly what the roadmap's own "Verify" bullet defers to you doing real labeling.

## What to look out for

- **W&B is optional, confirmed working**: with `WANDB_API_KEY` blank (as it is in this environment), `start_run` logs an info message and returns `None`; `log_metrics`/`finish` no-op safely on `None`. A unit test also confirms `start_run` catches a `wandb.init()` failure (mocked, not a real network call) without propagating - training genuinely cannot fail because of W&B.
- **Every row (train + val + test) gets scored and stored**, not just train - `evaluate`/`report` (Stages 8-9) read back from `video_scores` filtered by split, which is the entire point of Stage 5's schema design: no need to hold the trained model in memory or re-run inference to evaluate later.
- `train_model` rejects an unrecognized `--model` value before doing any work (validated both at the CLI level and inside `train_model` itself).
- The `metadata.json` sidecar records exact library versions and row counts - useful for debugging "why did this model behave differently" months from now.

## How to run tests properly

```powershell
# 1. Unit tests - synthetic, perfectly-separable data, validates training MACHINERY only
uv run pytest tests/test_model_train.py tests/test_model_tracking.py -v
uv run pytest

# 2. Lint
uv run ruff check .

# 3. Once you have a real data/splits.csv:
uv run slop model train --model both
docker compose exec postgres psql -U slop -d slopornot -c "select model_name, count(*), avg(score) from video_scores group by 1;"
```
