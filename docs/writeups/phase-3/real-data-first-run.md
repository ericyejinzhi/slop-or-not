# First real-data run: ingest -> label -> splits -> features -> train -> evaluate (2026-10-05)

## What is being implemented

Not new code so much as the first time the whole pipeline ran against real YouTube data instead of synthetic fixtures. Everything before this (Phases 1-4) was built and tested on fixtures and real infrastructure only.

The sequence, all on a freshly re-ingested corpus:

1. **Reset**: every data table and the MinIO `thumbnails` bucket were wiped. The 380 old video-level labels were backed up to `.dev-logs/labels-backup-20261002.sql` first and not restored.
2. **Ingest**: `slop ingest seed-channels` over `data/seed_channels.csv`, default sample of 10 random videos per channel. Result: 60 channels, 626 videos, 42,386 comments, 617 thumbnails.
3. **Label**: per channel, in the web dashboard. 646 labels: 428 up, 200 down, 18 skip. Two channels (`@bingingwithbabish`, `@mrbeast`) were skipped entirely.
4. **Splits**: `slop label make-splits --group-by video` (the per-video option, which was briefly the default; see `phase-2/stage-6-train-val-test-split.md`): 608 non-skip videos, train 426 / val 91 / test 91, about 31-32% down in each.
5. **Features**: `slop features compute-nlp` (626 videos) and `compute-vision` (617 videos with a thumbnail).
6. **Train and evaluate**: `slop model train --model both`, then `evaluate` on val and test and `report` for XGBoost on test.

Code changes that came out of it: the per-video split option, the 512-token sentiment truncation fix (see `DEVIATIONS.md`), and then `slop model cv` once the leakage became clear (see `cross-validation.md`).

## What it should look like

**These by-video numbers are inflated by channel leakage; the honest channel-grouped result is PR-AUC about 0.59 (XGBoost) / 0.60 (logistic regression), F1 about 0.5. See `cross-validation.md`.** The table below is kept as the record of the first run.

Positive class is slop (label "down"). "Caught / missed" is slop videos found / not found.

| Model | Split | PR-AUC | F1 | Caught / missed | False alarms |
|---|---|---|---|---|---|
| Majority baseline | val / test | 0.319 / 0.308 | 0.000 | none caught | 0 |
| `logistic_regression/20261006-005632` | val | 0.678 | 0.610 | 18 / 11 | 12 |
| `logistic_regression/20261006-005632` | test | 0.822 | 0.633 | 19 / 9 | 13 |
| `xgboost/20261006-005636` | val | 0.981 | 0.912 | 26 / 3 | 2 |
| `xgboost/20261006-005636` | test | 0.995 | 0.902 | 23 / 5 | 0 |

XGBoost's five test misses (predicted not-slop, labeled slop) include `'The 18 Pro Max Champion?'`, two `'Warning ... Scary Videos'` titles from one channel, a sports highlight and `'Best Indian Dosa'`. It flagged no good video as slop on test.

## What to look out for

- **These scores are almost certainly inflated by channel leakage.** Labels are per channel, so every video in a channel shares one label, and the by-video split puts the same channel in train, val and test. A tree model can reach very high scores just by recognizing a channel's titles, thumbnails and upload cadence. The gap between XGBoost (0.98-0.99) and the more constrained logistic regression (0.68-0.82) fits that picture. This run shows the pipeline works end to end; it does not show the model has learned what slop is.
- **The honest number has since been measured**, with stratified channel-grouped k-fold (`slop model cv`): XGBoost PR-AUC 0.589 +/- 0.125, logistic regression 0.599 +/- 0.091, baseline 0.312. The leaky by-video k-fold gives XGBoost 0.989, which confirms the gap above is leakage. A single channel-grouped val/test split would have only about 8-9 channels each and be very noisy, which is why cross-validation is the better tool.
- **Per-channel metrics are meaningless here.** Each channel has 1-5 videos per split and a single label, so per-channel PR-AUC is `nan` and F1 is mostly 0 or 1.
- **Small splits**: 91 videos each, so one video moves F1 by about a point.
- **Logistic regression did not converge** (lbfgs hit 1000 iterations, scikit-learn's convergence warning). Features are unscaled; scaling them would likely help. Its numbers are weaker than they need to be.
- **Missing values are expected, not errors**: of 626 videos, 7 have no scoreable comments (null sentiment and comment embedding), 69 have no description embedding, and 53 have no comment-topic clusters. XGBoost handles nulls natively; check what the logistic regression pipeline imputes before trusting it.
- **Operational lessons**: each `slop` command takes about a minute to start (torch/prefect imports); NLP scoring of ~42k comments on CPU took over two hours and was cut off once by a background-task time limit (it resumes with `--only-missing`); and one retrain was killed by the OS's low-memory protection - free memory before long runs.
- **Not done yet**: `slop model ablation` under channel-grouped CV, SHAP report, promoting a model to active (`ACTIVE_MODEL_NAME`/`ACTIVE_MODEL_VERSION`), and anything AWS.

## How to run tests properly

```powershell
# Re-run the whole sequence from labeled data (each command is slow to start, run in the background)
uv run slop label make-splits                       # default: --group-by channel
uv run slop label make-splits --group-by video      # the leaky per-video option (this run used it)
uv run slop model cv --folds 5 --repeats 3          # the honest estimate, no splits.csv needed
uv run slop features compute-nlp --only-missing
uv run slop features compute-vision --only-missing
uv run slop model train --model both
uv run slop model evaluate --model-name xgboost --model-version <version> --split val
uv run slop model evaluate --model-name xgboost --model-version <version> --split test
uv run slop model report   --model-name xgboost --model-version <version> --split test

# Sanity-check feature coverage in Postgres
docker compose exec -T postgres psql -U slop -d slopornot -c "select count(*) from video_nlp_features"   # expect 626
docker compose exec -T postgres psql -U slop -d slopornot -c "select count(*) from video_vision_features" # expect 617

# Unit tests for the two code changes
uv run pytest tests/test_label_split_video.py tests/test_features_sentiment.py -m "not slow" -v
```
