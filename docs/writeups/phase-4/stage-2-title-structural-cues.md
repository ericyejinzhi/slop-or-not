# Phase 4, Stage 2 - Title structural cues (pure, no ML)

## What is being implemented

Four structural title cues from the roadmap's title-intent bullet: curiosity-gap phrase count, unresolved-pronoun count, ALL-CAPS span count, and ellipsis count. Pure regex/string functions, no ML - these are cheap, free metadata-only signal that don't need an embedding model to compute.

Files: `src/sloppy/features/title_structure.py` (new), `src/sloppy/features/extract.py` (extended - 4 new `VideoFeatures` fields), `src/sloppy/models/train.py` (all 4 added to `NUMERIC_FEATURES`).

## What it should look like

```python
>>> from sloppy.features.title_structure import *
>>> curiosity_gap_phrase_count("Here's why this happened")
1
>>> unresolved_pronoun_count("This is her secret")
2
>>> all_caps_span_count("This is INSANE and CRAZY")
2
>>> ellipsis_count("wait for it...")
1
```

## What to look out for

- **A deliberate deviation from the plan, worth flagging**: the plan's own summary said "add the 3 count fields to `NUMERIC_FEATURES`" while listing 4 functions. Since the roadmap itself names all 4 structural cues (curiosity-gap phrases, unresolved pronouns, ALL-CAPS spans, ellipses) as equally-weighted signals with no stated reason to exclude one, I included all 4 in `NUMERIC_FEATURES` rather than arbitrarily dropping `title_ellipsis_count`. Flagging this in case there was an intended reason to exclude it that didn't make it into the plan text.
- `unresolved_pronoun_count` matches whole words only via `re.findall(r"[a-zA-Z']+", ...)`, not substring matching - "history" does not count as containing "his" (verified with a dedicated test), which a naive `"his" in text` check would have gotten wrong.
- `all_caps_span_count` requires at least 2 consecutive capital letters (`{2,}`), so a lone capitalized "I" doesn't count as a shouty span - verified explicitly.
- **This stage caused an expected regression in Phase 3's existing model-training tests**, not a new bug: `tests/test_model_train.py`'s synthetic fixture builds rows with a fixed column set matching the old (smaller) `NUMERIC_FEATURES` list. Adding 4 new required columns meant that fixture was suddenly missing columns pandas needed. Fixed by adding the 4 new fields (as neutral constant `0` values, since they're not the fixture's separating signal) to the fixture. This is the expected cost of growing the shared feature list - every extension to `NUMERIC_FEATURES`/`CATEGORICAL_FEATURES` from here through Stage 12 will likely need the same fixture update.
- Fully and permanently testable without real data - deterministic string transformations, same category as Stage 2's `features/text.py` from Phase 3.

## How to run tests properly

```powershell
uv run pytest tests/test_features_title_structure.py tests/test_features_extract.py -v
uv run pytest    # full suite - 94 tests now, confirms the NUMERIC_FEATURES extension didn't break training
uv run ruff check .
```
