# Phase 3, Stage 9 - Error-analysis report

## What is being implemented

`slop model report --model-name --model-version --split test` - the top-N most confidently wrong predictions (false positives and false negatives), sorted by `|score - 0.5|` descending, joined against video titles/channels for readability. This is the roadmap's "error-analysis notebook," built as a CLI report instead (see the Context section of the overall plan and the `phase-3-overview.md` for the reasoning) - the underlying `top_errors` function is plain enough that a notebook could still be layered on top later if you want plots/interactive exploration.

- `src/sloppy/models/report.py` - `top_errors`.
- `src/sloppy/cli.py` - command `report`.

## What it should look like

```
$ uv run slop model report --model-name logistic_regression --model-version 20260926-005801 --split train --n 5

Top false positives (predicted down, actually up) (0):
  (none)

Top false negatives (predicted up, actually down) (0):
  (none)
```

(This is real output - on the perfectly-separable synthetic corpus used to test Stages 7-8, there are genuinely zero errors, which is itself a useful thing to have confirmed: the "no errors" path renders cleanly rather than crashing on an empty result.) Against real, messier data you'd expect to see rows like:

```
Top false positives (predicted down, actually up) (3):
  score=0.891  'Some Video Title'  (UC_somechannelid)
  ...
```

## What to look out for

- **The genuinely interesting part of error analysis - actually looking at *why* the model is wrong on real videos - can only happen once real labels and real scores exist.** This stage only proves the mechanism works: the DB join (video_scores + videos + canonical labels), the sorting, the empty-result handling. `top_errors` itself is thoroughly unit-tested with synthetic scores/labels covering filtering, sorting, the `n` limit, and an invalid `kind` argument.
- Ranking is by confidence (`|score - 0.5|`), not by how wrong the raw label mismatch is - a false positive scored 0.99 is a much more interesting error to look at than one scored 0.51, and this ordering surfaces the former first.
- If you want a notebook later for richer exploration (plots, side-by-side thumbnail viewing, etc.), it can call `top_errors`/`evaluate` directly rather than reimplementing anything - those functions were kept plain and dependency-light specifically so this stays an option, not a rewrite.

## How to run tests properly

```powershell
# 1. Unit tests - fully synthetic, no DB needed
uv run pytest tests/test_model_report.py -v
uv run pytest   # full suite, 90 tests as of the end of Phase 3

# 2. Lint
uv run ruff check .

# 3. Once you have a trained, scored model:
uv run slop model report --model-name <name> --model-version <version> --split test --n 20
```
