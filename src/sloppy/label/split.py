"""Channel-grouped, stratified train/val/test split.

No scikit-learn dependency (reserved for Phase 3) - a seeded greedy bin-packing heuristic
assigns whole channels to splits, balancing split size and up/down ratio against targets.
Never splits a single channel's videos across sets.
"""

import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from sloppy.db.models import Label, Video

Split = str  # "train" | "val" | "test"


def canonical_labels(session: Session) -> dict[str, tuple[str, str]]:
    """video_id -> (channel_id, label): each video's most-recent non-skip label.
    Videos whose only label(s) are 'skip' are excluded - they never received an actual
    judgment, so they can't be training ground truth."""
    stmt = (
        select(Label.video_id, Label.label, Label.created_at)
        .where(Label.label != "skip")
        .order_by(Label.video_id, Label.created_at.desc())
    )
    rows = session.execute(stmt).all()
    channel_by_video = dict(session.execute(select(Video.id, Video.channel_id)).all())

    canonical: dict[str, tuple[str, str]] = {}
    seen: set[str] = set()
    for row in rows:
        if row.video_id in seen:
            continue
        seen.add(row.video_id)
        channel_id = channel_by_video.get(row.video_id)
        if channel_id is not None:
            canonical[row.video_id] = (channel_id, row.label)
    return canonical


@dataclass
class ChannelLabelStats:
    channel_id: str
    up: int
    down: int

    @property
    def total(self) -> int:
        return self.up + self.down


def channel_stats(canonical: dict[str, tuple[str, str]]) -> list[ChannelLabelStats]:
    counts: dict[str, list[int]] = {}
    for channel_id, label in canonical.values():
        counts.setdefault(channel_id, [0, 0])
        if label == "up":
            counts[channel_id][0] += 1
        else:
            counts[channel_id][1] += 1
    return [
        ChannelLabelStats(channel_id=cid, up=up, down=down) for cid, (up, down) in counts.items()
    ]


def assign_channels_to_splits(
    stats: list[ChannelLabelStats],
    proportions: tuple[float, float, float] = (0.70, 0.15, 0.15),
    seed: int = 42,
    balance_weight: float = 0.5,
) -> dict[str, Split]:
    """Whole channels assigned, never split. Deterministic given seed.

    1. Seeded-shuffle channel order (avoid input-order bias).
    2. Sort descending by total (largest-first bin-packing heuristic).
    3. For each channel, assign to whichever split has the largest remaining need
       *relative to its own target* (a proportional-fill heuristic - see note below),
       adjusted by a balance penalty for how far that split's up-ratio would land from
       the overall up-ratio after adding this channel.
    """
    names: tuple[Split, Split, Split] = ("train", "val", "test")
    total_videos = sum(s.total for s in stats)
    total_up = sum(s.up for s in stats)
    overall_up_ratio = total_up / total_videos if total_videos else 0.0
    target_counts = {name: p * total_videos for name, p in zip(names, proportions, strict=True)}

    ordered = list(stats)
    random.Random(seed).shuffle(ordered)
    ordered.sort(key=lambda s: s.total, reverse=True)

    running_total = dict.fromkeys(names, 0)
    running_up = dict.fromkeys(names, 0)
    assignment: dict[str, Split] = {}

    for stat in ordered:
        best_split: Split | None = None
        best_score = float("-inf")
        for name in names:
            target = target_counts[name]
            # Fraction of this split's OWN target still unfilled. Using a target-relative
            # deficit (not an absolute one) is what makes this self-balance across splits
            # of very different sizes: comparing raw deviations biases the greedy choice
            # toward whichever split's target is numerically closest to zero (val/test),
            # since a small target is "satisfied" by far fewer videos in absolute terms.
            remaining_ratio = (target - running_total[name]) / target if target > 0 else -1.0

            new_total = running_total[name] + stat.total
            new_up = running_up[name] + stat.up
            new_ratio = new_up / new_total if new_total else overall_up_ratio
            balance_penalty = abs(new_ratio - overall_up_ratio)

            score = remaining_ratio - balance_weight * balance_penalty
            if score > best_score:
                best_score = score
                best_split = name

        assert best_split is not None
        assignment[stat.channel_id] = best_split
        running_total[best_split] += stat.total
        running_up[best_split] += stat.up

    return assignment
