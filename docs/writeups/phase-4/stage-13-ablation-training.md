# Phase 4, Stage 13 - Ablation-capable training + `slop model ablation`

## What is being implemented

`train.py`'s `build_preprocessor`/`train_model`/`score_dataframe` are now parameterized over explicit `numeric_features`/`categorical_features` lists instead of reading module-level constants - `TrainedModel` grew `numeric_features`/`categorical_features` fields (plus an `all_features` property) so `score_dataframe` always uses the trained model's own feature list, not a global. Three cumulative `FEATURE_GROUPS` are defined: `metadata` (Phase 3 + Stage 2's structural cues), `metadata_text` (+ everything sentiment/embedding/title-intent-derived), `all` (+ everything CLIP-derived). `slop model ablation` trains the same estimator on all 3 groups, persists each under a distinguishing `model_name` (e.g. `xgboost_metadata`), and prints a side-by-side comparison table via the new `src/sloppy/models/ablation.py::format_ablation_table`.

## What it should look like

Run for real against a synthetic 80-video corpus with real NLP/vision features computed (same style of setup as Stage 7/9's smoke tests):

```
$ uv run slop model ablation --model xgboost --split val
Training xgboost_metadata on 60 row(s)...
  saved to models_artifacts\xgboost\20260926-201230\model.joblib
Training xgboost_metadata_text on 60 row(s)...
  saved to models_artifacts\xgboost\20260926-201231\model.joblib
Training xgboost_all on 60 row(s)...
  saved to models_artifacts\xgboost\20260926-201233\model.joblib

feature_group  n  pr_auc  f1  baseline_f1
     metadata 10     1.0 1.0          0.0
metadata_text 10     1.0 1.0          0.0
          all 10     1.0 1.0          0.0
```

`SELECT DISTINCT model_name, model_version FROM video_scores` afterward shows all 3 variants (`xgboost_metadata`, `xgboost_metadata_text`, `xgboost_all`) coexisting side by side with their own versions - exactly the point of `video_scores`' composite key design from Stage 5 (Phase 3).

## A real, informative edge case surfaced during testing (not a bug)

The synthetic corpus used only 3 comments per video. `cluster_comment_topics` (Stage 6) correctly requires at least `MIN_COMMENTS_FOR_CLUSTERING = 5` comments before attempting KMeans, so every video's `topic_cluster_count`/`topic_top_cluster_share`/`topic_top_cluster_sentiment`/`topic_sentiment_spread` came back `None`. With every row missing those same 4 columns, scikit-learn's `SimpleImputer` can't compute a median from an all-`NaN` column and prints `UserWarning: Skipping features without any observed values` - but it still proceeds correctly (fills with a default), and training completed successfully across all 3 feature groups. This is worth remembering once real data arrives: **any topic-cluster feature will be entirely absent for a training batch where every video has fewer than 5 scored comments** - not a crash, but a silent "this feature contributed nothing" for that run.

## What to look out for

- **Real, end-to-end verification across all 3 feature groups**, not just unit-tested plumbing: the command was actually run against a real (if synthetic) 80-video corpus with real sentiment/embedding/CLIP features computed via the actual Stage 5-9 pipelines, and all 3 variants trained, persisted valid `model.joblib`/`metadata.json` artifacts, and scored/upserted correctly into `video_scores` under distinct model names.
- **Every existing `slop model evaluate`/`report` command works unmodified against any ablation variant** - no new evaluation code was written for this stage; `ablation_command` just calls the existing `evaluate()` function 3 times with different training data and prints the results in one table, exactly the "extend, don't duplicate" approach from the plan.
- Perfect separation (F1=1.0) across all 3 groups in the real run above is expected, not surprising - the synthetic corpus's duration-to-label correlation is a perfectly learnable signal by design (same as every prior Phase 3/4 training smoke test), so this only proves the pipeline wiring works, not that any feature group is "better" - that question needs real labeled data.
- `channel_title_self_similarity` and the two text-derived interactions live in the `TEXT` group (not `VISION`), even though `channel_thumbnail_self_similarity` (its close cousin) lives in `VISION` - the split follows what the feature is actually *derived from* (title embeddings vs. image embeddings), not surface-level naming similarity. Worth double-checking if you ever add a new feature to the wrong group by pattern-matching on its name.

## How to run tests properly

```powershell
uv run pytest tests/test_model_ablation.py tests/test_model_train.py -v
uv run pytest    # full suite - 124 passed, 5 deselected
uv run ruff check .

# Real end-to-end check (needs data/splits.csv plus compute-nlp/compute-vision already run):
uv run slop model ablation --model xgboost --split val
docker compose exec postgres psql -U slop -d slopornot -c \
  "SELECT DISTINCT model_name, model_version FROM video_scores ORDER BY model_name;"
```
