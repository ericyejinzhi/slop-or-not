# Phase 3, Stage 8 - Evaluation (PR-AUC, F1, confusion matrix, per-channel, majority baseline)

## What is being implemented

`slop model evaluate --model-name --model-version --split val|test` reads persisted `video_scores` + canonical labels back from the DB (no need to hold the trained model in memory) and prints PR-AUC/F1/confusion-matrix metrics for the model vs. the majority-class baseline, both overall and per-channel - the per-channel breakdown is the roadmap's own leakage smell test.

- `src/sloppy/models/evaluate.py` - `_binary_metrics` (the one building block, called once for the overall set and once per channel group via the same function - this is what makes per-channel a byproduct rather than separately-implemented logic), `majority_class_baseline` (the mode of the **train** split's `y` - never val/test), `evaluate`.
- `src/sloppy/cli.py` - command `evaluate`.

## What it should look like

```
$ uv run slop model evaluate --model-name logistic_regression --model-version 20260926-005434 --split val
Evaluation for logistic_regression v20260926-005434 on 'val' split:
  model   : n=10 pr_auc=1.000 f1=1.000 tp=5 fp=0 tn=5 fn=0
  baseline: n=10 pr_auc=0.500 f1=0.000 tp=0 fp=0 tn=5 fn=5

Per-channel:
  UC_smoke_eval_6: n=10 pr_auc=1.000 f1=1.000 tp=5 fp=0 tn=5 fn=0
```

This is real output from a real run against the same synthetic corpus described in Stage 7 - the model achieves perfect separation while the majority baseline (predicting one class for everyone) scores F1=0, a genuine "beats the baseline convincingly" result on synthetic data.

## What to look out for

- **"Beats the baseline convincingly" is left as your own qualitative read of the printed numbers**, not a hardcoded pass/fail threshold - it would be premature to bake in a specific bar (e.g. "F1 must exceed X") before you've seen what real YouTube labels actually produce.
- **PR-AUC is `nan` for any group with only one class present** (e.g. a channel where every video happens to share the same label) - `average_precision_score` isn't meaningful without both classes, so this is reported as `nan` rather than a misleading number. Verified with a dedicated unit test.
- The majority-class baseline is computed from the **train** split's labels only, never from the split being evaluated - evaluating against a baseline derived from the same data you're scoring would be circular.
- Per-channel output was verified against a deliberately "leaky" synthetic scenario (one channel with suspiciously perfect separation, another with realistic noise) to confirm the per-channel breakdown actually surfaces the difference rather than averaging it away.

## How to run tests properly

```powershell
# 1. Unit tests - fully synthetic y/score/channel_id arrays, no DB needed
uv run pytest tests/test_model_evaluate.py -v
uv run pytest

# 2. Lint
uv run ruff check .

# 3. Once you have a trained model (from `slop model train`):
uv run slop model evaluate --model-name <name> --model-version <version> --split val
uv run slop model evaluate --model-name <name> --model-version <version> --split test
```
