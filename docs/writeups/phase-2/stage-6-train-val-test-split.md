# Phase 2, Stage 6 - Train/val/test split (channel-grouped, dependency-free)

## What is being implemented

`slop label make-splits` turns whatever's in the `labels` table into a `data/splits.csv` artifact (`video_id,channel_id,label,split`) for Phase 3 to consume - a channel-grouped, approximately-stratified train/val/test split with no scikit-learn dependency.

- `canonical_labels(session)` - each video's most-recent **non-skip** label; skip-only videos are excluded entirely (they never got an actual judgment).
- `channel_stats()` - per-channel up/down counts.
- `assign_channels_to_splits()` - a seeded greedy algorithm that assigns *whole channels* to train/val/test, never splitting one channel's videos across sets, while targeting both a size proportion (default 70/15/15) and the corpus's overall up/down ratio in each split.
- `data/splits.csv` is **not committed to git** - it's mechanically reproducible from `labels` + a fixed `--seed`, unlike the hand-curated `seed_channels.csv`, and your existing `.gitignore` already covers it via the `data/*` rule.

## Two real algorithm bugs found and fixed during this stage

The split algorithm isn't just "assign videos randomly to bins" - assigning whole *channels* to bins of very different target sizes (70% vs 15% vs 15%) is a bin-packing problem, and my first two attempts at the cost function were both wrong in ways that only showed up once I actually ran it:

1. **First attempt** normalized each split's size-cost by its *own* target count. This meant a nearly-empty val/test bin (target 90) looked "more satisfied" by a small channel than the same channel would look to the much bigger train bin (target 420), purely because 90 is a smaller number to get close to. Result on a 60-channel test corpus: train ended up with only **40%** of the data instead of 70%.
2. **Second attempt** normalized by total corpus size instead - which fixed the previous bias but introduced a new one: comparing *raw* deviation-from-target still favors whichever split's target is numerically closest to zero when everything starts at zero. Result: train got **0%** - even worse.
3. **The actual fix**: compare each split's remaining need *as a fraction of that split's own target* (not an absolute or corpus-normalized deviation), i.e. "what fraction of val's goal is still unmet" vs. "what fraction of train's goal is still unmet" - directly comparable regardless of how different the target sizes are. This is a standard proportional-fill heuristic once framed this way, and it works: a 60-channel test landed at 69.5/14.8/15.7 (target 70/15/15), with the up/down ratio within half a percentage point across all three splits.

I caught both bugs because I wrote the proportion/balance assertions into the automated tests *before* trusting the implementation, then additionally stress-tested with a more realistic synthetic corpus (uneven channel sizes 15-30, five different per-channel label ratios) rather than stopping at the uniform-channel test case - that's what exposed how far off the first two attempts actually were.

## What it should look like

```
$ uv run slop label make-splits
Wrote 342 labeled video(s) to data\splits.csv
  train: 240
  val: 51
  test: 51
```

Every row for a given `channel_id` in `splits.csv` should show the same `split` value - no channel ever spans two splits.

## What to look out for

- **Verified against real Postgres with synthetic data**, not the real corpus (still empty, pending your API key + channel curation): inserted 6 synthetic channels x 8 videos each (with one video per channel deliberately labeled `skip`), ran `make-splits` for real, and confirmed the output CSV excluded all 6 skip-labeled videos and kept every channel entirely within one split.
- `assign_channels_to_splits` takes a `balance_weight` (default 0.5) trading off size-proportion accuracy against label-ratio balance. At real Phase 2 scale (40-80 channels), size proportions should land close to target; if your corpus has a few channels that are wildly skewed toward one label, the balance term will sometimes accept a slightly worse size fit to avoid concentrating all the slop (or all the quality) videos into one split - that's intentional, not a bug, but worth knowing if the split sizes look slightly uneven.
- The algorithm is deterministic given `--seed` (default 42) - re-running with the same seed on the same label data reproduces the exact same split, which is what makes it safe to leave out of git.
- `--proportions` takes 3 comma-separated floats that must sum to 1.0; the CLI validates this and fails cleanly rather than producing a silently-wrong split.

## How to run tests properly

```powershell
# 1. Full suite - pure unit tests against synthetic ChannelLabelStats, no DB needed
uv run pytest tests/test_label_split.py -v
uv run pytest

# 2. Lint
uv run ruff check .

# 3. Once you have real labels:
uv run slop label make-splits
# confirm no channel spans two splits:
python -c "
import csv
from collections import defaultdict
rows = list(csv.DictReader(open('data/splits.csv')))
by_channel = defaultdict(set)
for r in rows:
    by_channel[r['channel_id']].add(r['split'])
bad = {c: s for c, s in by_channel.items() if len(s) > 1}
print('channels spanning multiple splits (should be empty):', bad)
"
```
