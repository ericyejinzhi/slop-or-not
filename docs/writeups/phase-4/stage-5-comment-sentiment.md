# Phase 4, Stage 5 - Comment sentiment

## What is being implemented

`src/sloppy/features/sentiment.py`: `score_comments` runs `cardiffnlp/twitter-roberta-base-sentiment-latest` (a pretrained 3-way sentiment classifier) over comment texts and reduces each to a single `P(positive) - P(negative)` score in `[-1, 1]`; `aggregate_sentiment` rolls per-comment scores up into per-video stats (mean, std, negative share, a hand-curated "slop keyword" hit rate); `channel_sentiment_rollup` averages video-level sentiment up to channel level. Not yet persisted - Stage 7.

## What it should look like

```python
>>> from sloppy.features.sentiment import score_comments, aggregate_sentiment
>>> scores = score_comments(["this is amazing content", "worst video ever, total slop"])
>>> scores
[0.93, -0.87]  # illustrative - real run confirmed correct sign, not these exact values
>>> aggregate_sentiment(["amazing", "terrible"], scores)
SentimentAggregate(sentiment_mean=0.03, sentiment_std=0.9, sentiment_negative_share=0.5,
                    slop_keyword_rate=0.0, comment_count_scored=2)
```

## What to look out for

- **Verified against the real model, not just mocked.** The `@pytest.mark.slow` test ran the real `cardiffnlp/twitter-roberta-base-sentiment-latest` checkpoint (downloaded ~500MB on first run, cached afterward) against two hand-typed sentences and confirmed the sign came out right: positive for "this is amazing content," negative for "worst video ever, total slop." Same Windows symlink-cache warning as Stage 3 - harmless, already documented.
- **`aggregate_sentiment`/`channel_sentiment_rollup` take precomputed scores, not a model** - they're pure functions, fully and permanently testable without ever loading anything. Only `score_comments` touches the real pipeline. This mirrors the split already used in `features/duration.py` (pure math) vs. `features/embeddings.py` (the one thing that loads a model) from earlier stages.
- **`SLOP_KEYWORDS` is a small, hand-curated lexicon** (`"ai slop"`, `"bot"`, `"farm"`, `"reused content"`, `"recycled"`, `"clickbait"`), same treatment as `features/text.py`'s clickbait phrase list from Phase 3 - deliberately simple, explicitly flagged for revisit once real comment data and error analysis (Stage 9's report, extended for Phase 4 features) show what's actually predictive.
- The cardiffnlp checkpoint is 3-way (negative/neutral/positive); `score_comments` drops the neutral probability from the final score rather than trying to use all 3 classes as separate features - a comment classified mostly "neutral" naturally lands near 0 in the resulting `[-1, 1]` score, which is the intended behavior, not a bug.
- `aggregate_sentiment([], [])` returns every field as `None` (except `comment_count_scored=0`) rather than raising or returning `0.0` - a video with zero scoreable comments (e.g., comments disabled) should look like "no data," not "neutral sentiment."

## How to run tests properly

```powershell
uv run pytest tests/test_features_sentiment.py -v         # 7 fast tests, no model needed
uv run pytest tests/test_features_sentiment.py -m slow -v  # real model, real sentence-level check
uv run pytest    # full suite - 103 passed, 3 deselected (Phase 4's slow tests so far)
uv run ruff check .
```
