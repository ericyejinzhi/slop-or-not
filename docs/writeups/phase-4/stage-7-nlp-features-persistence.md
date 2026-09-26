# Phase 4, Stage 7 - `video_nlp_features` table + persistence + `slop features compute-nlp`

## What is being implemented

The `video_nlp_features` table persists everything Stages 4-6 compute: sentiment aggregates, comment-topic clustering aggregates, title-intent scores, and three embeddings (title, description, mean comment) as `pgvector` `Vector(384)` columns. `slop features compute-nlp` (new `features_app` CLI sub-app) is the orchestration command: per video, fetch comments, score sentiment, embed everything, cluster comment topics, score title intent, upsert.

Files: `src/sloppy/db/models.py` (`VideoNlpFeatures`), `alembic/versions/c931a905226f_add_video_nlp_features_table.py`, `src/sloppy/features/nlp_store.py` (`upsert_video_nlp_features`), `src/sloppy/cli.py` (new `features_app`, `compute-nlp` command).

## A known gotcha, hit exactly as predicted

Alembic's autogenerate produced `pgvector.sqlalchemy.vector.VECTOR(dim=384)` in the migration's `create_table` call **without ever importing `pgvector.sqlalchemy`** - the plan flagged this as a known rough edge before I even ran the command, and it happened exactly as described. Fixed by adding `import pgvector.sqlalchemy` to the migration file by hand before applying it. Worth remembering for Stage 9's `video_vision_features` migration too.

## What it should look like

This was run for real against a synthetic video (no real YouTube data ingested yet, so a hand-inserted video + 6 comments):

```
$ uv run slop features compute-nlp --video-id smoke_compute_nlp_video
  smoke_compute_nlp_video: 6 comment(s) scored
Computed NLP features for 1 video(s).
```

Real persisted values, queried back with `psql`, for a video titled *"You Won't Believe What Happened Next!!!"* with 6 comments (2 negative, one mentioning "bot farm"):

| column | value |
|---|---|
| `comment_count_scored` | 6 |
| `sentiment_mean` | 0.335 |
| `sentiment_negative_share` | 0.333 (= 2/6) |
| `slop_keyword_rate` | 0.167 (= 1/6, the "bot farm" comment) |
| `topic_cluster_count` | 5 |
| `title_lure_score` | 0.600 |
| `title_transparent_score` | 0.166 |
| `vector_dims(title_embedding)` | 384 |

## What to look out for

- **This is real, end-to-end verification, not a synthetic-fixture-only check.** Every number above matches hand-computable expectations exactly: 2 of 6 comments are negative (0.333), exactly 1 comment contains a slop keyword (0.167), and - most tellingly - the deliberately lure-styled title scored 0.600 on `title_lure_score` vs. 0.166 on `title_transparent_score`, which is the semantic signal Stage 4 exists to produce, now flowing all the way through persistence.
- **Idempotency was verified directly**: ran `compute-nlp` twice against the same video and confirmed exactly one row survives (`SELECT count(*) ... = 1`), consistent with the upsert-on-`video_id` design (unlike `video_scores`' composite key).
- **`video_nlp_features` is keyed on `video_id` alone**, not `(video_id, model_name, model_version)` like `video_scores` - a deliberate difference. These are inputs consumed by exactly one downstream training run at a time; there's no product need to compare "sentiment under checkpoint A vs. B" side by side the way model predictions get compared. Checkpoint names (`sentiment_model`, `embedding_model`) are plain provenance columns, not part of the key - re-running with a new checkpoint just overwrites.
- Comment embeddings themselves are never persisted per-comment - only their mean (`comment_embedding_mean`) is stored, consistent with the project-wide rule that comment-level model outputs are transient, only video-level aggregates persist.
- If a video has zero comments, `compute-nlp` still runs cleanly: `sentiment_scores`/`comment_embeddings` are empty, `aggregate_sentiment`/`cluster_comment_topics` both correctly degrade to `None`-filled aggregates (verified by their own Stage 5/6 unit tests), and only the title-based fields (embedding, intent scores) get real values.
- Not yet wired into the training dataset (`assemble_dataset`) - that's Stage 12.

## How to run tests properly

```powershell
docker compose up -d
uv run pytest tests/test_db_models.py tests/test_features_nlp_store.py -v
uv run pytest    # full suite - 108 passed, 3 deselected

uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d video_nlp_features"
uv run alembic downgrade -1 ; uv run alembic upgrade head   # reversibility

uv run ruff check .

# Real end-to-end check (needs at least one ingested video with comments):
uv run slop features compute-nlp --video-id <a real ingested video id>
docker compose exec postgres psql -U slop -d slopornot -c \
  "SELECT sentiment_mean, title_lure_score, vector_dims(title_embedding) FROM video_nlp_features WHERE video_id = '<that id>';"
```
