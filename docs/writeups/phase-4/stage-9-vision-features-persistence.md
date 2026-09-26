# Phase 4, Stage 9 - `video_vision_features` table + persistence + `slop features compute-vision`

## What is being implemented

The `video_vision_features` table persists Stage 8's CLIP image embedding (`Vector(512)`) and 3 zero-shot scalar scores. `slop features compute-vision` orchestrates: for every video with a `Thumbnail` row, download the image from MinIO, embed it, score it against the zero-shot prompts, upsert. FK to `videos.id` (not `thumbnails.video_id`) - decouples vision-feature recompute from any particular thumbnail row's lifecycle, same reasoning as `video_nlp_features`.

Files: `src/sloppy/db/models.py` (`VideoVisionFeatures`), `alembic/versions/33b9bfb38fd8_add_video_vision_features_table.py`, `src/sloppy/features/vision_store.py`, `src/sloppy/cli.py` (`compute-vision` command).

## The known `pgvector.sqlalchemy` import gotcha, hit again exactly as expected

Same as Stage 7's migration: autogenerate emitted `pgvector.sqlalchemy.vector.VECTOR(dim=512)` without importing `pgvector.sqlalchemy`. Fixed the same way - added the import by hand before applying. Two-for-two now; this is clearly just how this version of Alembic's autogenerate handles pgvector columns, not a one-off fluke.

## What it should look like

Run for real against a synthetic video (no real ingested thumbnails yet) using the same fixture image from Stage 8, uploaded to MinIO first:

```
$ uv run slop features compute-vision --video-id smoke_compute_vision_video
  smoke_compute_vision_video: embedded + scored
Computed vision features for 1 video(s).
```

Real persisted values, queried back:

| column | value |
|---|---|
| `vector_dims(image_embedding)` | 512 |
| `clip_clickbait_score` | 0.203 |
| `clip_ai_generated_score` | 0.230 |
| `clip_text_heavy_score` | 0.216 |
| `clip_model` | `openai/clip-vit-base-patch32` |

## What to look out for

- **Real end-to-end verification, including a real MinIO round-trip**: the fixture JPEG was actually uploaded to the `thumbnails` bucket, then `compute-vision` downloaded it back, ran it through the real CLIP model, and persisted a real 512-dim embedding plus 3 real (not mocked) zero-shot scores. Re-running against the same video was confirmed idempotent (`count(*) = 1` before and after).
- **Per-thumbnail failures don't abort the whole run** - `compute_vision`'s loop wraps `load_thumbnail_image`/`embed_image`/`zero_shot_scores` in a try/except and logs a warning per video rather than crashing, matching Phase 1's `_ingest_video` philosophy (one bad item shouldn't lose progress on the rest).
- Videos with no `Thumbnail` row at all are simply excluded from the query (an inner `join`, not a left join) - `compute-vision` only ever attempts videos it has a real thumbnail location for.
- Same keying/upsert rationale as `video_nlp_features` (Stage 7): `video_id` alone, not a composite key like `video_scores` - vision features are inputs to training, not predictions to compare across checkpoints.

## How to run tests properly

```powershell
docker compose up -d
uv run pytest tests/test_db_models.py tests/test_features_vision_store.py -v
uv run pytest    # full suite - 110 passed, 5 deselected

uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d video_vision_features"
uv run alembic downgrade -1 ; uv run alembic upgrade head   # reversibility

uv run ruff check .

# Real end-to-end check (needs at least one ingested video with a thumbnail):
uv run slop features compute-vision --video-id <a real ingested video id>
docker compose exec postgres psql -U slop -d slopornot -c \
  "SELECT vector_dims(image_embedding), clip_clickbait_score FROM video_vision_features WHERE video_id = '<that id>';"
```
