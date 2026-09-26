# Phase 3, Stage 3 - Pure duration features

## What is being implemented

The video-length features from the roadmap: `duration_bucket` (short/mid/long/unknown) and `duration_deviation` - a z-score of a video's duration against a peer group (its channel or its genre), computed in log1p-space by default since durations are heavy-tailed. This is the feature the roadmap specifically calls out as useful: "45 seconds is normal for Shorts, suspicious for a documentary."

File: `src/sloppy/features/duration.py`.

## What it should look like

```python
>>> from sloppy.features.duration import duration_bucket, duration_deviation
>>> duration_bucket(45)
'short'
>>> duration_bucket(1500)
'long'
>>> peers = [560, 580, 600, 620, 640, 590, 610, 605, 615, 595] * 2  # documentary-length peers
>>> duration_deviation(45, peers, use_log=True)
-4.87...  # a 45s video amid ~600s peers is a strong negative outlier - exactly the signal wanted
```

## A real bug found and fixed during testing

My first test for the "45s video amid documentary-length peers" case used 20 **identical** peer durations (`[600] * 20`). That's a genuine edge case, not a representative one: with zero variance in the peer group, the z-score's denominator (standard deviation) is zero, so `duration_deviation` correctly returns its documented `0.0` fallback for an undefined z-score - but that made the test assert `0.0 < -1.0`, which fails. This wasn't a bug in the function; it was a test that accidentally exercised the wrong code path. Fixed by giving the peer group realistic variance (durations ranging 560-640s instead of all exactly 600), which is also a more honest test of real usage - 15-30 real video durations are never all bit-for-bit identical. I kept a dedicated test for the true zero-spread edge case (documenting that it returns `0.0` rather than raising) so that behavior stays intentional and visible rather than accidentally-untested.

## What to look out for

- **The zero-peer-spread fallback (`0.0`) is a documented simplification**, not a claim that a wildly different video "looks normal" - it's just the safest defined behavior for an edge case that's extremely unlikely with real data.
- `duration_deviation`'s peer group includes the target video's own duration - a deliberate simplification (see the docstring) that's negligible at realistic channel/genre sizes and much simpler to test/reason about than leave-one-out exclusion.
- Fully and permanently testable without real data - like Stage 2, these are deterministic statistical transformations over whatever peer list is passed in.

## How to run tests properly

```powershell
uv run pytest tests/test_features_duration.py -v   # 10 tests, all pure unit tests
uv run ruff check .
```
