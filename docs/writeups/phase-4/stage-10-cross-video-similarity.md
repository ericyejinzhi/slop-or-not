# Phase 4, Stage 10 - Cross-video similarity features

## What is being implemented

`src/sloppy/features/similarity.py` - three pgvector cosine-distance queries, computed at dataset-assembly time and **not persisted** (no new table, same pattern as `features/corpus.py`'s corpus stats being rebuilt fresh every run):

- `channel_thumbnail_self_similarity_mean` - a video's mean thumbnail-embedding distance to every other video in its own channel (the "templated-ness" signal the roadmap calls "the novel signal").
- `near_duplicate_thumbnail_count` - corpus-wide (not channel-scoped) count of thumbnails within a cosine-distance threshold of this one.
- `channel_title_self_similarity_mean` - the same idea applied to title embeddings, a text-templated-ness signal symmetric to the thumbnail one.

Uses pgvector's `<=>` cosine-distance operator directly via raw SQL (`text()`), since querying doesn't need the ORM `Vector` type - only the column definition does.

## What it should look like

```python
>>> from sloppy.features.similarity import channel_thumbnail_self_similarity_mean
>>> channel_thumbnail_self_similarity_mean(session, "some_video_id", "some_channel_id")
0.12  # low = this video's thumbnail looks like the rest of its channel's thumbnails
```

## What to look out for

- **This is the strongest kind of verification available before real data exists**: exact, hand-computable expected values from known vectors, not just "runs without crashing." Three videos were inserted with real pgvector-typed embeddings - two identical unit vectors and one orthogonal to both - so the expected cosine distances are exactly `0.0` and `1.0` by construction, not approximate. `channel_thumbnail_self_similarity_mean` correctly returned `0.5` (the average of 0 and 1), `near_duplicate_thumbnail_count` correctly returned `1` (only the identical twin counts, not the orthogonal one), and the parallel title-embedding version returned the same `0.5` from an analogous 384-dim setup. All three passed on the first run.
- **`NEAR_DUPLICATE_COSINE_DISTANCE = 0.05` is a judgment call**, explicitly flagged for revisit once real thumbnail embeddings exist - there's no principled way to pick this threshold without seeing what real near-duplicate thumbnails' distances actually look like.
- **These queries return `None` gracefully when there's nothing to compare against** - a video with no `video_vision_features`/`video_nlp_features` row yet (not run through Stages 7/9's compute commands), or a channel with no other videos that have embeddings, correctly returns `None` rather than a SQL error or a division-by-zero. Verified directly with a video that has zero rows in `video_vision_features`.
- `channel_thumbnail_self_similarity_mean` joins `videos` twice (once for "mine," once scoping "other" to the same `channel_id`) - this is what makes it channel-scoped, in contrast to `near_duplicate_thumbnail_count`, which is deliberately corpus-wide per the roadmap's own framing ("# near-duplicate thumbnails across corpus").
- Not yet wired into `assemble_dataset` - that's Stage 12.

## How to run tests properly

```powershell
docker compose up -d
uv run pytest tests/test_features_similarity.py -v
uv run pytest    # full suite - 112 passed, 5 deselected
uv run ruff check .
```
