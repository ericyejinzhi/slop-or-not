# Phase 3, Stage 2 - Pure text features

## What is being implemented

The title/description text features from the roadmap's feature list: `caps_ratio`, `emoji_count`, `clickbait_score` (a small hand-curated phrase lexicon), `description_length`, `tag_count`. Pure stdlib, zero ML dependency - `src/sloppy/features/` stays dependency-free through Stage 4, which matters for how easy these are to test.

File: `src/sloppy/features/text.py`.

## What it should look like

```python
>>> from sloppy.features.text import caps_ratio, emoji_count, clickbait_score
>>> caps_ratio("YOU WON'T BELIEVE THIS!!!")
1.0
>>> emoji_count("great video 😱😱 check it out")
2
>>> clickbait_score("How to replace a bike chain")
0.0
```

## What to look out for

- **`clickbait_score`'s lexicon is deliberately simple and hand-curated, not learned** - a fixed list of phrases (`"you won't believe"`, `"shocking"`, `"top 10"`, `"!!!"`, etc.) divided by word count. This is a baseline-appropriate placeholder; the roadmap itself expects this kind of feature to get refined once real error analysis (Stage 9) shows what's actually predictive. Don't read too much into its current phrase list - it's a starting point, not a tuned model.
- These functions are **fully and permanently testable without any real data** - they're deterministic string transformations, not statistics over a corpus. Nothing here will ever need real labels to verify.
- `emoji_count`'s regex covers the common emoji Unicode ranges (misc symbols/pictographs, dingbats, emoticons) but isn't exhaustive of every Unicode emoji ever added - fine for a baseline feature, not claimed to be complete.

## How to run tests properly

```powershell
uv run pytest tests/test_features_text.py -v   # 9 tests, all pure unit tests
uv run ruff check .
```
