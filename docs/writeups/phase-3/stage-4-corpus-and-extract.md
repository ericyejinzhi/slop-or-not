# Phase 3, Stage 4 - Corpus stats + feature combiner

## What is being implemented

The layer that turns Stages 2-3's per-video functions into full per-video feature records, computed against the whole ingested corpus: `primary_genre` (extracts a display genre from YouTube's `topicDetails` URLs), `upload_cadence_days` (median days between a channel's uploads), `build_corpus_stats` (groups durations by channel and by genre, and publish dates by channel, across every ingested video), and `extract_features` (combines everything into one `VideoFeatures` record per video).

Files: `src/sloppy/features/corpus.py`, `src/sloppy/features/extract.py`.

## A real bug found and fixed during testing

`upload_cadence_days` computes gaps between consecutive sorted publish dates via `zip(ordered, ordered[1:], strict=True)`. This is wrong by construction: `ordered` and `ordered[1:]` are a list and its own tail, so they're **always** exactly one element different in length - `strict=True` demands equal lengths and would raise `ValueError` on every single call with 2+ elements, not just an edge case. Both a direct unit test and, downstream, `extract_features`'s own test caught this immediately (both failed with the same `ValueError`). Fixed by removing `strict=True` - ruff's `B905` rule then correctly flagged the bare `zip()` as needing an explicit `strict=` value, so it's now `strict=False` with a comment explaining why the length mismatch is intentional here.

## What it should look like

```python
>>> from sloppy.features.corpus import primary_genre, upload_cadence_days
>>> primary_genre(["https://en.wikipedia.org/wiki/Gaming"])
'Gaming'
>>> upload_cadence_days([datetime(2026,1,1), datetime(2026,1,3), datetime(2026,1,9)])
2.0  # median gap: 2 days, then 6 days -> median 2
```

`extract_features(video, corpus)` returns a `VideoFeatures` record combining every field from Stages 2-4 - title stats, duration stats (including deviation from the video's own channel and genre norms), engagement ratios, cadence, and genre.

## What to look out for

- **`build_corpus_stats` should be built from ALL ingested videos, not just labeled ones** - channel/genre duration norms need to reflect the real corpus, not be skewed by whichever subset happened to get labeled. This is enforced in Stage 6's `assemble_dataset`, not here - this stage just builds the mechanism; it's agnostic to which videos you feed it.
- `VideoLike`/`ExtractableVideo` are `typing.Protocol`s, not concrete base classes - they're satisfied by ORM `Video` rows directly (duck typing) and by small hand-written `@dataclass` fakes in tests, without needing a shared inheritance hierarchy or touching the DB in tests.
- Fully and permanently testable without real data - verified with a hand-built fake corpus (3 channels x 5 videos, 2 genres) where every expected value (durations grouped correctly, cadence computed correctly, a specific video's full feature record matching hand-computed values) was checked explicitly.

## How to run tests properly

```powershell
uv run pytest tests/test_features_corpus.py tests/test_features_extract.py -v   # 9 tests
uv run ruff check .
```
