# Phase 4, Stage 6 - Comment topic clustering

## What is being implemented

`src/sloppy/features/comment_topics.py::cluster_comment_topics` - KMeans (k=5, fixed, per the roadmap's "KMeans, or BERTopic once comfortable" - BERTopic explicitly deferred) over precomputed comment embeddings, producing per-video aggregates: how many distinct topic clusters appear, what share of comments fall in the largest one, that cluster's mean sentiment, and the spread of sentiment *across* clusters. This last one is the roadmap's actual signal: "slop tends to draw a narrow, repetitive comment distribution; genuine content spreads across topics." Pure numpy/sklearn - zero model-loading in this file; the caller (Stage 7) supplies embeddings via `features/embeddings.py` and sentiments via `features/sentiment.py`, both already computed for other purposes.

## What it should look like

```python
>>> from sloppy.features.comment_topics import cluster_comment_topics
>>> cluster_comment_topics(embeddings, sentiments)  # 20 comments, tightly clustered, similar sentiment
TopicAggregate(topic_cluster_count=5, topic_top_cluster_share=0.3,
                topic_top_cluster_sentiment=0.51, topic_sentiment_spread=0.02)
```

Fewer than 5 comments (`MIN_COMMENTS_FOR_CLUSTERING`) returns every field as `None` - KMeans with k=5 degenerates below that many points, and the aggregates wouldn't mean anything.

## What to look out for

- **One test in this stage produces an exact, hand-computable expected value despite going through real KMeans clustering** - worth understanding why, since that's unusual for a clustering algorithm. Five points placed at maximally-separated, scaled one-hot locations in 5D with `k=5` requested forces KMeans to assign each point its own singleton cluster, *regardless of which internal label index it assigns to which point*. That symmetry means `topic_cluster_count` (5), `topic_top_cluster_share` (exactly `1/5`, since every cluster ties at size 1), and `topic_sentiment_spread` (the population stdev of the 5 sentiment values themselves, order-independent) are all exactly predictable without needing to know or control KMeans' internal tie-breaking. Only `topic_top_cluster_sentiment` is left as "one of the 5 known values" since which singleton wins the argmax tie isn't something worth pinning down.
- A second test uses a tight, low-variance synthetic blob (20 points, small Gaussian noise in both embedding space and sentiment) to confirm the "narrow, repetitive" case actually produces low `topic_sentiment_spread` - the qualitative behavior the roadmap's whole rationale for this feature rests on.
- `topic_cluster_count` counts only clusters that actually received at least one point (`np.count_nonzero(cluster_sizes)`) - with k=5 fixed but very few real distinct topics in genuinely repetitive comments, some of the 5 requested clusters can end up empty, and this correctly reports the smaller number rather than always reporting 5.
- Fully and permanently testable without real data or a real model - this file's own tests never touch `sentence-transformers` or `transformers` at all, only synthetic numpy arrays.

## How to run tests properly

```powershell
uv run pytest tests/test_features_comment_topics.py -v
uv run pytest    # full suite - 106 passed, 3 deselected (Stages 3/4/5's slow tests)
uv run ruff check .
```
