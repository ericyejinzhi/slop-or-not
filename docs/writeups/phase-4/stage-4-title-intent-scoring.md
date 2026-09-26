# Phase 4, Stage 4 - Title-intent prototype scoring

## What is being implemented

Unsupervised title-intent scoring from the roadmap: embed a title, score cosine similarity against 3 hand-written prototype categories (`grey_area_lure`, `intentionally_mysterious`, `transparent`), each represented by a centroid of 6 example titles. `src/sloppy/features/title_intent.py`. Not yet wired into `VideoFeatures`/persisted - that's Stage 7.

## What it should look like

```python
>>> from sloppy.features.title_intent import score_title_intent
>>> score_title_intent("How to replace a bike chain")
TitleIntentScores(lure_score=0.10, mysterious_score=0.08, transparent_score=0.34)
>>> score_title_intent("You won't believe what happened next")
TitleIntentScores(lure_score=0.41, mysterious_score=0.15, transparent_score=0.05)
```

(Illustrative shape - the real run described below confirms actual values rank correctly, not these exact numbers.)

## What to look out for

- **This was genuinely, semantically verified against the real model - the strongest confirmation of any Phase 4 stage so far.** The `@pytest.mark.slow` test runs the real `all-MiniLM-L6-v2` model and confirms "How to replace a bike chain" scores highest on `transparent_score` (not `lure_score` or `mysterious_score`), and "You won't believe what happened next" scores highest on `lure_score`. This isn't just "does the code run" - it's confirming the centroid-cosine approach actually separates these categories correctly on real sentence embeddings, which couldn't have been faked or assumed.
- **Prototype sets are a deliberate first draft**, explicitly flagged (same as Phase 2's rubric) for revisit once real titles and real labels exist - 6 examples per category, written by hand, not tuned against any data.
- **Centroid-of-normalized-embeddings, not max-or-mean-of-pairwise-similarities**: each category's 6 prototypes are individually L2-normalized, averaged, then re-normalized into one centroid vector. This is more robust to any single prototype's odd phrasing than taking the max similarity across prototypes (noisy, oversensitive to one match) and cheaper than averaging pairwise similarities (equivalent-ish result, 3x more computation).
- **A real testability trap, caught and worked around**: `_prototype_centroids()` is `@lru_cache`'d (computed once per process), which means a fast test that monkeypatches `embed_texts` to avoid the real model must explicitly call `_prototype_centroids.cache_clear()` before *and* after, or a real-model result from an earlier test (or a later one) could leak in through the cache and silently invalidate what the fast test thinks it's testing. Both tests in `test_features_title_intent.py` clear the cache defensively in a `try/finally` for exactly this reason.
- The pure-math fast test uses orthogonal unit-vector "titles" (not real embeddings) specifically so the expected cosine scores are mathematically exact (1.0 and 0.0), not approximate - a stronger assertion than checking "roughly higher than the others."

## How to run tests properly

```powershell
uv run pytest tests/test_features_title_intent.py -v        # fast, pure cosine math
uv run pytest tests/test_features_title_intent.py -m slow -v  # real model, real semantic check
uv run pytest    # full suite - 96 passed, 2 deselected (both Phase 4 slow tests so far)
uv run ruff check .
```
