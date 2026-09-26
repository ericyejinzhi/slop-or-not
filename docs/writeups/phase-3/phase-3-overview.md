# Phase 3 - Baseline model (full write-up)

This covers the whole of Phase 3 end-to-end. For stage-by-stage detail, see `stage-1-ml-dependencies.md` through `stage-9-error-analysis.md` in this same directory.

## What is being implemented

The first real ML in the project: metadata-only feature engineering, a logistic regression + XGBoost baseline classifier, persisted model artifacts, a `video_scores` table, evaluation against a majority-class baseline (overall and per-channel, to catch leakage), best-effort W&B tracking, and an error-analysis report.

Built across nine stages:

1. **ML dependencies** (scikit-learn, xgboost, pandas, numpy, wandb) + W&B config fields.
2. **Text features** (`src/sloppy/features/text.py`) - caps ratio, emoji count, clickbait score, description length, tag count.
3. **Duration features** (`src/sloppy/features/duration.py`) - bucket + deviation-from-peer-norm (channel and genre).
4. **Corpus stats + feature combiner** (`corpus.py`, `extract.py`) - per-channel/genre aggregates, upload cadence, one flat `VideoFeatures` record per video.
5. **`video_scores` table** (`src/sloppy/db/models.py`, a migration, `src/sloppy/models/scores.py`) - upserted, keyed on `(video_id, model_name, model_version)`.
6. **Dataset assembly** (`src/sloppy/features/dataset.py`) - `data/splits.csv` + full corpus -> one training-ready DataFrame.
7. **Model training** (`src/sloppy/models/train.py`, `tracking.py`, `slop model train`) - logistic regression + XGBoost, best-effort W&B, persisted artifacts, scores every video into `video_scores`.
8. **Evaluation** (`src/sloppy/models/evaluate.py`, `slop model evaluate`) - PR-AUC/F1/confusion matrix vs. majority baseline, overall and per-channel.
9. **Error analysis** (`src/sloppy/models/report.py`, `slop model report`) - top-N most confidently wrong predictions.

## Architecture, end to end

```
data/splits.csv (from Phase 2's `slop label make-splits`)
        |
        v
load_splits() -> assemble_dataset()  (features/dataset.py)
        |               |
        |    build_corpus_stats() over ALL ingested videos (features/corpus.py)
        |               |
        |    extract_features() per labeled video (features/extract.py, using
        |    features/text.py + features/duration.py)
        v
  training DataFrame (one row per labeled video: features + y + split)
        |
   slop model train --model logistic_regression|xgboost|both
        |
        +--> build_preprocessor() + estimator -> sklearn Pipeline  (models/train.py)
        +--> save_model() -> models_artifacts/<name>/<version>/{model.joblib,metadata.json}
        +--> best-effort W&B run (models/tracking.py - no-ops without WANDB_API_KEY)
        +--> score_dataframe() -> upsert_video_score() for every row  (models/scores.py)
                    |
                    v
              video_scores table
                    |
        +-----------+-----------+
        v                       v
  slop model evaluate      slop model report
  (models/evaluate.py)     (models/report.py)
  PR-AUC/F1/confusion,     top-N false positives/
  per-channel, vs.         negatives, most
  majority baseline        confidently wrong first
```

Every table/module follows the conventions established in Phases 1-2: `Base`/`TimestampMixin`, no ORM `relationship()`, `session_scope()` for all writes, one test file per module, `_cleanup()`-guarded live-Postgres integration tests alongside pure unit tests.

## What it should look like

Once you have real labeled data (`data/splits.csv` from Phase 2):

```
$ uv run slop model train --model both
Training logistic_regression on <N> row(s)...
  saved to models_artifacts\logistic_regression\<version>\model.joblib
  scored <M> video(s), version=<version>

$ uv run slop model evaluate --model-name logistic_regression --model-version <version> --split val
Evaluation for logistic_regression v<version> on 'val' split:
  model   : n=... pr_auc=... f1=... tp=... fp=... tn=... fn=...
  baseline: n=... pr_auc=0.500 f1=... tp=... fp=... tn=... fn=...

Per-channel:
  ...

$ uv run slop model report --model-name logistic_regression --model-version <version> --split test --n 20
Top false positives (predicted down, actually up) (...):
  score=0.89  'Some Video Title'  (UCsomechannel)
  ...
```

## What to look out for

- **Three real bugs were found and fixed during implementation, not just theoretical risks:**
  1. `upload_cadence_days` (Stage 4) used `zip(ordered, ordered[1:], strict=True)` to pair a list against its own tail - `strict=True` demands equal-length inputs, but a list and its tail are *never* the same length, so this raised `ValueError` on every single call. Caught immediately by both a direct unit test and `extract_features`'s downstream test. Fixed by using `strict=False` with a comment explaining why the length mismatch is intentional.
  2. A duration-deviation test (Stage 3) used 20 *identical* peer durations to test "a short video among long peers," which accidentally exercised the documented zero-variance edge case (returns `0.0`, since a z-score is undefined with no spread) instead of the intended signal. Not a bug in the function - a test that tested the wrong thing. Fixed by giving the peer group realistic variance.
  3. `mimetypes`-style extension-from-content-type problems don't recur here (that was Phase 2), but the same "verify, don't assume" discipline caught both bugs above before they could hide inside "looks reasonable" code.
- **No real labeled data exists yet anywhere in this environment.** `data/seed_channels.csv` is still header-only, `data/splits.csv` doesn't exist, `.env`'s `YOUTUBE_API_KEY`/`LABELER_NAME` are blank. Every stage was still verified for real: Stages 2-4 are pure functions verified with hand-computed expected values (permanently, no real data ever needed); Stages 5, 6, 8, 9 were verified against your live dev Postgres with synthetic fixtures (inserted, exercised, cleaned up every time); Stage 7 (training) was run **through the real CLI** against a synthetic 80-video corpus with a deliberately learnable signal, and both models correctly separated the classes (logistic regression: ~0.99999 vs ~0.0000015; XGBoost: ~0.967 vs ~0.033) - proving the entire training -> persistence -> scoring -> DB pipeline works, though not proving anything about real predictive power on real YouTube videos.
- **W&B is best-effort, confirmed working**: with no `WANDB_API_KEY` configured, training runs completely normally and just skips tracking (logged at info level, not a warning) - verified both by direct testing and by a unit test that mocks `wandb.init()` failing outright and confirms it doesn't propagate.
- **One test-isolation lesson from this session, worth remembering**: while testing Stages 7-9, I left synthetic scored data in the DB between two smoke tests, and it caused an unrelated *pre-existing* Phase 2 test (`consistency_sample`'s random-sampling test) to fail transiently, because that test samples from the *global* label pool without scoping to its own test data. Not a bug I introduced, but a reminder that this test suite shares live DB state across files - clean up synthetic data immediately after each manual check, don't defer it.
- **`video_scores.score` = P(label == "down")**, matching the project's "slop or not" framing (higher = more suspicious) - easily flippable later if you'd rather it be P(quality), but currently baked into the 0.5 threshold used everywhere.
- **Error analysis is a CLI report, not a Jupyter notebook** - the roadmap says "notebook," but a notebook adds a dependency, is hard to verify non-interactively, and can't show anything meaningful until real data exists anyway. `top_errors`/`evaluate` stay plain enough that a notebook can be layered on top later without a rewrite.

## How to run tests properly

```powershell
# 1. Bring up the dev stack
docker compose up -d

# 2. Full automated suite - 90 tests as of the end of Phase 3, including several that
#    hit the live dev Postgres directly (video_scores upserts, dataset assembly)
uv run pytest -v

# 3. Lint
uv run ruff check .

# 4. Migration + schema sanity check
uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d video_scores"

# 5. CLI wiring sanity check (no real data needed)
uv run slop model --help
uv run python -c "import sklearn, xgboost, pandas, numpy, wandb; print('all imports ok')"

# 6. The piece that needs your own real data:
#    a. Finish Phase 2 for real: curate data/seed_channels.csv, set YOUTUBE_API_KEY and
#       LABELER_NAME, ingest, label, run `slop label make-splits`
#    b. uv run slop model train --model both
#    c. uv run slop model evaluate --model-name <name> --model-version <version> --split val
#    d. uv run slop model evaluate ... --split test
#    e. uv run slop model report --model-name <name> --model-version <version> --split test
#    f. Read the roadmap's own verify bullet with real numbers in hand: does either model
#       beat the majority baseline convincingly? The CLI prints both side by side - the
#       judgment call is yours.
```

## What's next

Phase 3's code is complete; the remaining work is entirely about getting real data (Phase 2's curation/labeling) and then actually running this pipeline against it. Per `ROADMAP.md`, Phases 1-3 together already constitute a complete "data pipeline + baseline model" story - a natural place to pause if momentum stalls. If continuing, Phase 4 ("the ML heart") is next: comment sentiment, comment-topic clustering, unsupervised title-intent scoring, text/thumbnail embeddings via pgvector, cross-video similarity, and feature interactions - a deeper feature set built on top of everything Phase 3 established.
