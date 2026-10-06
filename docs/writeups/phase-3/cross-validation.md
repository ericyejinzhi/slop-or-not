# Stratified, channel-grouped k-fold cross-validation (2026-10-06)

## What is being implemented

`slop model cv` (code: `src/sloppy/models/cv.py`, command in `src/sloppy/cli.py`) estimates how well the models generalize to **channels they have never seen**, using k-fold cross-validation instead of one val/test split.

- Folds come from scikit-learn's `StratifiedGroupKFold`, with `channel_id` as the group and the up/down label as the stratification target. Each channel sits entirely inside one fold, and the slop/non-slop mix is balanced across folds. A plain `StratifiedKFold` would put a channel in both train and test again, which is exactly the leakage this exists to remove.
- Every non-skip labeled video is held out exactly once per repeat, scored by a model trained on the other folds. The command reports per-fold metrics, the mean, standard deviation, min and max across folds, the majority-class baseline for comparison, and the pooled out-of-fold metrics (all predictions at once).
- `--repeats N` re-partitions the channels N times with different seeds (seed + repeat), because with about 58 channels a single partition is noisy.
- `--group-by video` switches to plain `StratifiedKFold`. It is kept only to measure the leakage gap.
- `--feature-group` picks `metadata`, `metadata_text` or `all`, same groups as `slop model ablation`.
- Reads labels and features straight from the database, so it does not need `data/splits.csv`. It saves no models and does not write `video_scores`.
- It refuses to run (a clear `[FAIL]`) if the rarer class has fewer channels than folds. Labels are per channel, so the check counts channels, not videos.

Tests: `tests/test_model_cv.py` (9 tests: no channel shared between train and test, every video tested once, label stratification, the video mode really does leak, determinism, argument validation, out-of-fold collection, repeats).

## What it should look like

Real run, 608 labeled videos from 58 channels (the other 2 are skip-only), all features, 5 folds:

| Model | Grouping | PR-AUC (mean +/- std) | F1 (mean +/- std) | Pooled out-of-fold PR-AUC / F1 |
|---|---|---|---|---|
| Majority baseline | any | 0.312 +/- 0.022 | 0.000 | - |
| Logistic regression | channel, 3 repeats | 0.599 +/- 0.091 | 0.544 +/- 0.082 | 0.569 / 0.543 |
| XGBoost | channel, 3 repeats | 0.589 +/- 0.125 | 0.501 +/- 0.158 | 0.592 / 0.536 |
| Logistic regression | video, 1 repeat (leaky) | 0.755 +/- 0.071 | 0.659 +/- 0.049 | 0.743 / 0.660 |
| XGBoost | video, 1 repeat (leaky) | 0.989 +/- 0.009 | 0.942 +/- 0.024 | 0.989 / 0.942 |

Reading it:

- **The leakage was real and large for XGBoost.** The same model, same features, same labels: PR-AUC 0.989 when folds are by video, 0.589 when folds are by channel. About 0.4 of the apparent skill came from recognizing channels it had already seen. The earlier val/test numbers (0.98-0.995) were measuring that, not slop detection.
- **There is real signal on new channels.** Both models roughly double the baseline PR-AUC (about 0.6 vs 0.31). That is the honest result for "classify a channel the model has never seen".
- **It is far from reliable.** F1 is about 0.5 and the folds swing a lot: XGBoost PR-AUC ranges from 0.34 to 0.80 across individual folds, and its F1 from 0.32 to 0.85. A fold has only 10-12 channels, so a handful of channels decides a fold.
- **XGBoost has no edge over logistic regression here.** With channel grouping the two are statistically indistinguishable (0.59 vs 0.60, both with a standard deviation of 0.09-0.13). XGBoost's advantage in the leaky setting came from memorizing channels, which logistic regression does less well.

## What to look out for

- **Folds are not independent samples.** Overlapping training sets and repeats that reuse the same 58 channels make the standard deviation a rough guide, not a confidence interval. Treat differences of a few hundredths as noise.
- **The label is per channel, so there are effectively 58 labeled examples** (about 19 slop, 39 not). Videos within a channel are heavily correlated. More channels would help more than more videos per channel.
- **Logistic regression emitted convergence warnings** (scikit-learn `lbfgs` hit its 1000-iteration limit; features are not scaled). Adding a scaler would likely help it; not done, since it would change the model used everywhere else.
- **Channel-level features still look at the whole channel.** Features such as upload cadence, channel sentiment, and similarity to the channel's own videos are computed from all of a channel's videos, including the held-out fold's. No labels are used, so it is not label leakage, but it is worth knowing.
- Per-fold numbers use thresholds of 0.5. PR-AUC does not depend on the threshold; F1 does, and with a 31% positive class the best threshold is probably lower. Not tuned.
- Run time: about a minute of CLI start-up, then a few minutes for 3 repeats of both models.

## How to run tests properly

```powershell
# The real thing (run in the background; the CLI takes about a minute to start)
uv run slop model cv --folds 5 --repeats 3                 # default: grouped by channel
uv run slop model cv --folds 5 --group-by video            # the leaky comparison
uv run slop model cv --model xgboost --feature-group metadata   # one model, fewer features

# Unit tests (no database needed)
uv run pytest tests/test_model_cv.py -v
uv run ruff check .
```
