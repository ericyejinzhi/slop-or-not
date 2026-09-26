# Phase 4 - NLP + vision features (full write-up)

This covers the whole of Phase 4 end-to-end. For stage-by-stage detail, see `stage-1-ml-dependencies.md` through `stage-14-shap-interaction-report.md` in this same directory.

## What is being implemented

The project's "ML heart" per `ROADMAP.md`: comment sentiment, comment-topic clustering, unsupervised title-intent scoring, text/thumbnail embeddings persisted via pgvector, cross-video similarity, hand-seeded feature interactions, an ablation-capable retrain of the fusion model, and a SHAP interaction report. This is the largest phase so far - it introduces the project's first heavy ML dependencies (PyTorch, transformers, sentence-transformers) and its first real use of the pgvector extension that has existed in Postgres, unused, since Phase 0.

Built across fourteen stages:

1. **ML dependencies** (CPU-only PyTorch via a dedicated uv index, transformers, sentence-transformers, pgvector, pillow, shap) + a new `slow` pytest marker so real-model tests stay out of the default fast run.
2. **Title structural cues** (`features/title_structure.py`) - curiosity-gap phrase count, unresolved-pronoun count, ALL-CAPS span count, ellipsis count. Pure regex, no model.
3. **Shared sentence-embedding wrapper** (`features/embeddings.py`) - `sentence-transformers/all-MiniLM-L6-v2`, 384-dim, `lru_cache`'d model load.
4. **Title-intent prototype scoring** (`features/title_intent.py`) - cosine similarity against 3 hand-written prototype centroids (`grey_area_lure`, `intentionally_mysterious`, `transparent`).
5. **Comment sentiment** (`features/sentiment.py`) - `cardiffnlp/twitter-roberta-base-sentiment-latest`, per-video aggregates + a slop-keyword rate + channel-level rollup.
6. **Comment topic clustering** (`features/comment_topics.py`) - KMeans over comment embeddings, per-cluster sentiment spread.
7. **`video_nlp_features` table + `slop features compute-nlp`** - persists sentiment/topic/title-intent scalars plus title/description/comment embeddings, keyed on `video_id` alone (upserted, not versioned like `video_scores`).
8. **CLIP embeddings** (`features/vision.py`) - `openai/clip-vit-base-patch32`, 512-dim image embeddings + 3 zero-shot prompt scores (clickbait, AI-generated, text-heavy).
9. **`video_vision_features` table + `slop features compute-vision`** - same upsert pattern as Stage 7, for CLIP-derived features.
10. **Cross-video similarity** (`features/similarity.py`) - pgvector `<=>` queries for channel-thumbnail self-similarity, corpus-wide near-duplicate thumbnail counts, and the same pair for title embeddings.
11. **Feature interactions** (`features/interactions.py`) - `lure_score_x_genre`, `duration_deviation_x_cadence`, `mysterious_score_x_duration_bucket`, seeded by hand per the roadmap's own reasoning about where these signals actually interact.
12. **Dataset assembly integration** (`features/dataset.py`) - wires all of the above into `assemble_dataset`, with graceful `None` degradation for videos not yet processed by `compute-nlp`/`compute-vision`.
13. **Ablation-capable training + `slop model ablation`** (`models/train.py`, `models/ablation.py`) - 3 cumulative `FEATURE_GROUPS` (`metadata`, `metadata_text`, `all`), each trained and persisted under its own `model_name`, printed side by side.
14. **SHAP interaction report** (`scripts/shap_interaction_report.py`) - standalone script, top-N feature-interaction pairs by mean absolute SHAP interaction value, for the README.

## Architecture, end to end

```
Video + Comment + Thumbnail rows (Phase 1 ingestion)
        |
        +----------------------+----------------------+
        v                                              v
slop features compute-nlp                    slop features compute-vision
        |                                              |
  score_comments() -> aggregate_sentiment()     load_thumbnail_image()
  embed_texts() -> cluster_comment_topics()     embed_image()
  score_title_intent()                          zero_shot_scores()
  embed_texts() (title/description/comments)          |
        |                                              |
        v                                              v
  video_nlp_features table                    video_vision_features table
  (sentiment/topic/title-intent scalars       (image_embedding + 3 CLIP
   + 3 pgvector embedding columns)              zero-shot scalar scores)
        |                                              |
        +----------------------+----------------------+
                               v
                    features/dataset.py::assemble_dataset()
                    (left-joins both tables, adds:
                     - similarity.py: pgvector <=> queries
                     - sentiment.py: channel_sentiment_rollup
                     - interactions.py: 3 hand-seeded crosses)
                               v
                  training DataFrame (metadata + text + vision columns)
                               v
                  slop model ablation --model xgboost --split val
                               |
              +----------------+----------------+
              v                v                v
      xgboost_metadata  xgboost_metadata_text  xgboost_all
      (train_model + evaluate, once per FEATURE_GROUPS entry)
                               |
                               v
                   video_scores (3 model_names coexist)
                               |
                               v
                scripts/shap_interaction_report.py
                (manual, one-off, needs a real "all" model)
```

Every table follows the conventions established in Phases 1-3: `Base`/`TimestampMixin`, no ORM `relationship()`, `session_scope()` for all writes, one test file per module, `_cleanup()`-guarded live-Postgres integration tests alongside pure unit tests. The two new tables (`video_nlp_features`, `video_vision_features`) deliberately deviate from `video_scores`' `(video_id, model_name, model_version)` composite key - they're keyed on `video_id` alone and upserted, since there's no product need to compare NLP/vision features across checkpoint versions the way model predictions get compared; checkpoint name is recorded as a plain provenance column instead.

## What it should look like

Once real labeled data and computed NLP/vision features exist:

```
$ uv run slop features compute-nlp
$ uv run slop features compute-vision
$ uv run slop model ablation --model xgboost --split val
Training xgboost_metadata on <N> row(s)...
  saved to models_artifacts\xgboost\<version>\model.joblib
Training xgboost_metadata_text on <N> row(s)...
  saved to models_artifacts\xgboost\<version>\model.joblib
Training xgboost_all on <N> row(s)...
  saved to models_artifacts\xgboost\<version>\model.joblib

feature_group        n  pr_auc   f1  baseline_f1
     metadata      <N>    ...   ...          ...
metadata_text      <N>    ...   ...          ...
          all      <N>    ...   ...          ...

$ uv run python scripts/shap_interaction_report.py models_artifacts/xgboost/<version>/model.joblib \
    --splits-csv data/splits.csv --split test
Wrote top 20 interaction pairs to docs/writeups/phase-4/shap-interactions.csv
```

Whether `+text` and `+vision` actually beat `metadata` alone - and whether the SHAP interactions match the hand-seeded crosses' intuition - is the qualitative question the roadmap leaves to real data, same as Phase 3's "beats the majority baseline convincingly."

## What to look out for

**Real bugs found and fixed during implementation** (not just theoretical risks - listed chronologically):

1. **Docker Desktop silently stopped** (Stage 1): the Windows `com.docker.service` had stopped in the background, so every DB-touching test hung indefinitely rather than failing fast - the connection attempt sat waiting on a port nothing was listening on. Diagnosed via a hard-timeout verbose pytest run to find the exact stuck test, confirmed via `docker compose ps` and `Get-Service`. Not a code bug, but easy to mistake for one; now a standing operational reminder in `TODO.md` (item 12).
2. **`pgvector.sqlalchemy` import omitted by Alembic autogenerate** (Stages 7 and 9, hit both times): autogenerate emits `pgvector.sqlalchemy.vector.VECTOR(dim=N)` in the migration file without importing `pgvector.sqlalchemy` - fixed by hand-adding the import each time. Confirmed as a real, repeatable tool quirk rather than a one-off mistake, since it recurred identically on the second vector-column migration.
3. **CLIP's `get_image_features`/`get_text_features` return shape** (Stage 8): the installed `transformers==5.17.0` returns a `BaseModelOutputWithPooling` object, not a bare tensor, so `.detach().numpy()` failed with `AttributeError`. Diagnosed via live introspection of the real return object (not guessed), fixed by reading `.pooler_output` first.
4. **`is None` vs. `pd.isna()`** (Stage 12): `pd.DataFrame.from_records` coerces mixed `None`/real-value columns to `NaN`, for both numeric and categorical/object columns - `is None` assertions failed with `assert np.float64(nan) is None`. Fixed by switching graceful-degradation assertions to `pd.isna(...)`.

**Recurring pattern across nearly every stage**: `tests/test_model_train.py`'s `_separable_dataframe()` fixture hand-builds a full row of feature columns, so every stage that added a new feature column required adding it to that fixture with a neutral value. Not a bug each time - an expected consequence of a growing feature set - but worth knowing if you extend `train.py`'s feature lists again later.

**No real labeled data exists yet anywhere in this environment** - `data/seed_channels.csv` is still header-only, `data/splits.csv` doesn't exist. Every stage was still verified for real, not just unit-tested in isolation:
- Stages 2, 6, 11 are pure functions verified with hand-computed expected values (permanent, no real data ever needed).
- Stages 3, 4, 5, 8 have a `@pytest.mark.slow` test that loads the real pretrained model and checks genuinely meaningful output (e.g. "How to replace a bike chain" scores highest on `transparent_score`; a positive-sentiment sentence scores positive).
- Stages 7, 9, 10 were verified against live dev Postgres with synthetic fixtures (inserted, exercised, cleaned up every time).
- Stage 13 got the deepest real verification of the phase: a synthetic 80-video corpus with **genuinely computed** NLP/vision features (real `score_comments`, `embed_texts`, `cluster_comment_topics`, `score_title_intent`, `embed_image`, `zero_shot_scores` calls, not mocked), run through the real `slop model ablation` CLI command, with all 3 model variants confirmed persisted distinctly in `video_scores` via `psql`.
- Stage 14's SHAP report has only its pure extraction function tested - running it against a real trained model is explicitly deferred, since no real "all features" model exists yet.

**Design decisions worth remembering**:
- Comment-level model outputs (per-comment embeddings, per-comment sentiment) are never persisted - only video-level aggregates. Raw embeddings never enter the fusion classifier as features, only scalar derived scores - at ~500 labels, raw 384/512-dim vectors would guarantee overfitting.
- No pgvector ANN index (ivfflat/hnsw) yet - exact cosine-distance scans are fast enough at a few-thousand-row scale; deferred until corpus size warrants it.
- Zero-shot CLIP scores are raw cosine similarities, not softmax-normalized across the prompt set, so each score stays independently meaningful and stable as prompts are added later.
- `channel_title_self_similarity` and its interactions live in the `TEXT` feature group, not `VISION`, even though its close cousin `channel_thumbnail_self_similarity` lives in `VISION` - the split follows what a feature is actually derived from (title vs. image embeddings), not surface-level naming.
- A synthetic corpus with fewer than 5 comments/video leaves every topic-cluster feature `None` for every row (Stage 13's `MIN_COMMENTS_FOR_CLUSTERING = 5`) - `SimpleImputer` handles this correctly (falls back to a default) but silently, worth remembering once real data arrives.

## How to run tests properly

```powershell
# 1. Bring up the dev stack (check it's actually running - see TODO.md item 12)
docker compose up -d
docker compose ps

# 2. Full fast suite - 127 passed, 5 deselected as of the end of Phase 4
uv run pytest

# 3. Slow suite - loads every real pretrained model (multi-minute on a cold cache)
uv run pytest -m slow

# 4. Lint
uv run ruff check .
uv run ruff format --check .

# 5. Migration + schema sanity check
uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d video_nlp_features"
docker compose exec postgres psql -U slop -d slopornot -c "\d video_vision_features"

# 6. CLI wiring sanity check (no real data needed)
uv run slop features --help
uv run slop model ablation --help
uv run python -c "import torch, transformers, sentence_transformers, pgvector, PIL, shap; print('ok')"

# 7. The pieces that need your own real data (see docs/writeups/TODO.md for the full list):
#    a. Finish Phase 2 for real (ingest, label, make-splits)
#    b. uv run slop features compute-nlp
#    c. uv run slop features compute-vision
#    d. uv run slop model ablation --model xgboost --split val   (and --split test)
#    e. uv run python scripts/shap_interaction_report.py <model.joblib path> --split test
```

## What's next

Phase 4's code is complete; the remaining work is entirely about getting real data (still blocked on Phase 2's curation/labeling, tracked in `docs/writeups/TODO.md`) and then actually running `compute-nlp`/`compute-vision`/`ablation`/the SHAP report against it to see whether the added features genuinely lift performance. Per `ROADMAP.md`, Phase 5 ("FastAPI service") is next: `GET /videos` (paginated, scores), `GET /videos/{id}` (score + feature breakdown + similar videos), `POST /ingest`, `POST /labels`, thumbnails served via presigned MinIO URLs, pydantic response schemas, pytest + httpx tests, and adding the API container to docker-compose. That phase will be the first consumer of everything Phase 3-4 built - `video_scores`, `video_nlp_features`, `video_vision_features`, and the similarity functions - from outside a CLI context.
