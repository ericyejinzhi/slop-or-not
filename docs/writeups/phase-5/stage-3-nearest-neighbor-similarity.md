# Phase 5, Stage 3 - Nearest-neighbor thumbnail similarity query

## What is being implemented

A new function `nearest_videos_by_thumbnail(session, video_id, k=10) -> list[tuple[str, float]]` added to `src/sloppy/features/similarity.py`, alongside Phase 4 Stage 10's three aggregate similarity functions. Those three all return a single scalar (a mean distance or a count) - none of them return a ranked list of actual nearest videos, which is exactly what `GET /videos/{id}`'s "similar videos" feature (Stage 5) needs. This function fills that gap using the same raw-SQL `text()` + pgvector `<=>` idiom as the rest of the file.

The query is corpus-wide, not channel-scoped - deliberately matching `near_duplicate_thumbnail_count`'s scope rather than the channel-scoped mean functions, since a "you might also like" strip is more useful when it isn't limited to one channel's own uploads.

## What it should look like

```sql
SELECT other.video_id, other.image_embedding <=> mine.image_embedding AS distance
FROM video_vision_features other
JOIN video_vision_features mine ON mine.video_id = :video_id
WHERE other.video_id != :video_id
ORDER BY distance ASC
LIMIT :k
```

```python
>>> nearest_videos_by_thumbnail(session, "video_a", k=5)
[("video_b", 0.02), ("video_c", 0.11), ("video_d", 0.34), ...]
```

Verified against the real dev Postgres with hand-picked, exact-cosine-distance fixture vectors (the same style as Phase 4's `test_features_similarity.py`): two videos with identical embeddings (distance 0) and one orthogonal to both (distance 1), confirming nearest-first ordering and exact distance values. A `k` truncation case and a "no embedding -> `[]`" case were also verified.

## What to look out for

- **The JOIN itself is what makes "no embedding" return `[]` automatically** - `mine` requires a matching `video_vision_features` row for `video_id`, so if that video has never had `compute-vision` run, the inner join to `mine` simply produces zero rows and the query returns `[]` without any special-cased existence check (unlike `near_duplicate_thumbnail_count`, which does an explicit `SELECT 1 ... WHERE video_id = :video_id` existence check first because it needs to distinguish "0 near-duplicates" from "no embedding to compare" as two different return values, `0` vs `None`). This function only has one "nothing to return" case, so the join alone suffices.
- **This function was added directly to the existing `similarity.py`, not a new module** - all 4 functions in this file now share the same raw-SQL idiom, so a reader scanning the file sees mean/count/nearest-list functions as siblings rather than split across files by return-shape.
- Distance ties (e.g. two videos with genuinely identical embeddings) are broken by whatever stable order Postgres happens to return - not something this function enforces, since there's no meaningful secondary sort key for "which near-duplicate should rank first."

## How to run tests properly

```powershell
uv run pytest tests/test_features_similarity.py -v
uv run pytest    # full suite
uv run ruff check .
```

Both new tests (`test_nearest_videos_by_thumbnail_orders_nearest_first_and_respects_k`, `test_nearest_videos_by_thumbnail_empty_without_embedding`) were added to the existing `tests/test_features_similarity.py`, reusing its `_unit_vector`/`_cleanup` helpers and `TEST_CHANNEL_ID`/`VIDEO_IDS` fixtures - real dev Postgres required (`docker compose up -d`).
