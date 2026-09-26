# Phase 3, Stage 5 - `video_scores` table + migration + upsert helper

## What is being implemented

The schema for storing a trained model's predictions. Unlike `labels` (append-only, since every human judgment is worth preserving), `video_scores` is **upserted**, keyed on the composite `(video_id, model_name, model_version)`: re-scoring with the same model version overwrites in place, while different model names/versions coexist side by side for comparison.

Files: `src/sloppy/db/models.py` (add `VideoScore`), `alembic/versions/75d8bc9ef5cf_add_video_scores_table.py`, `src/sloppy/models/scores.py` (`upsert_video_score`), `tests/test_db_models.py` (extended), `tests/test_model_scores.py` (new).

## What it should look like

- `psql \d video_scores` shows: `video_id`/`model_name`/`model_version` (composite PK), `score` (float, P(label == "down") - a "slop probability," higher = more suspicious), `predicted_label` (thresholded at 0.5, check-constrained to `'up'`/`'down'`), `split` (snapshotted at scoring time, so evaluation never needs to re-join `splits.csv`), plus `created_at`/`updated_at`.
- `uv run alembic current` prints `75d8bc9ef5cf (head)`.

## What to look out for

- **The upsert-vs-append-only decision is the important design call here.** A score is a reproducible function of a specific model version scoring a specific video - re-running that exact version should overwrite, not accumulate duplicate rows. This was verified directly: a live-Postgres test upserts the same `(video_id, model_name, model_version)` twice with different score/label values and confirms exactly one row survives with the latest values; a second test confirms two different model names for the same video coexist as separate rows.
- **`score` is P(label == "down")**, matching the project's own "slop or not" framing (higher = more suspicious) - not P(quality). This is a convention worth remembering when reading raw scores directly from the table; easy to flip later if you'd rather it be the other way, but it's baked into `predicted_label`'s 0.5 threshold and Stage 7's scoring code, so flipping it later means touching those too.
- Migration reviewed before applying (matches the model definition exactly) and round-tripped with `downgrade -1`/`upgrade head` to confirm reversibility - same discipline as every other migration in this project.

## How to run tests properly

```powershell
docker compose up -d
uv run pytest tests/test_db_models.py tests/test_model_scores.py -v
uv run alembic current
docker compose exec postgres psql -U slop -d slopornot -c "\d video_scores"
uv run alembic downgrade -1 ; uv run alembic upgrade head   # reversibility
```
