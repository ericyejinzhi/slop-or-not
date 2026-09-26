import random

from sloppy.label.split import ChannelLabelStats, assign_channels_to_splits, channel_stats


def test_channel_stats_counts_up_and_down_per_channel():
    canonical = {
        "v1": ("c1", "up"),
        "v2": ("c1", "down"),
        "v3": ("c2", "up"),
    }
    stats = {s.channel_id: s for s in channel_stats(canonical)}
    assert stats["c1"].up == 1
    assert stats["c1"].down == 1
    assert stats["c1"].total == 2
    assert stats["c2"].up == 1
    assert stats["c2"].down == 0


def _synthetic_stats(
    n_channels: int, videos_per_channel: int, up_ratio: float
) -> list[ChannelLabelStats]:
    rng = random.Random(0)
    stats = []
    for i in range(n_channels):
        up = round(videos_per_channel * up_ratio)
        down = videos_per_channel - up
        # jitter so channels aren't all identical
        jitter = rng.randint(-2, 2)
        up = max(0, up + jitter)
        down = max(1, down - jitter)
        stats.append(ChannelLabelStats(channel_id=f"c{i}", up=up, down=down))
    return stats


def test_assign_channels_to_splits_never_splits_a_channel():
    stats = _synthetic_stats(n_channels=40, videos_per_channel=10, up_ratio=0.5)
    assignment = assign_channels_to_splits(stats, seed=1)
    # every channel appears exactly once, in exactly one split
    assert set(assignment.keys()) == {s.channel_id for s in stats}
    assert set(assignment.values()) <= {"train", "val", "test"}


def test_assign_channels_to_splits_approximates_target_proportions():
    stats = _synthetic_stats(n_channels=60, videos_per_channel=10, up_ratio=0.5)
    assignment = assign_channels_to_splits(stats, proportions=(0.70, 0.15, 0.15), seed=1)

    totals = {"train": 0, "val": 0, "test": 0}
    for stat in stats:
        totals[assignment[stat.channel_id]] += stat.total

    grand_total = sum(totals.values())
    train_share = totals["train"] / grand_total
    val_share = totals["val"] / grand_total
    test_share = totals["test"] / grand_total

    assert abs(train_share - 0.70) < 0.08
    assert abs(val_share - 0.15) < 0.08
    assert abs(test_share - 0.15) < 0.08


def test_assign_channels_to_splits_preserves_overall_label_balance():
    stats = _synthetic_stats(n_channels=60, videos_per_channel=10, up_ratio=0.5)
    assignment = assign_channels_to_splits(stats, seed=1)

    overall_up = sum(s.up for s in stats)
    overall_total = sum(s.total for s in stats)
    overall_ratio = overall_up / overall_total

    for split_name in ("train", "val", "test"):
        split_up = sum(s.up for s in stats if assignment[s.channel_id] == split_name)
        split_total = sum(s.total for s in stats if assignment[s.channel_id] == split_name)
        if split_total == 0:
            continue
        split_ratio = split_up / split_total
        assert abs(split_ratio - overall_ratio) < 0.15


def test_assign_channels_to_splits_is_deterministic_given_seed():
    stats = _synthetic_stats(n_channels=20, videos_per_channel=10, up_ratio=0.4)
    first = assign_channels_to_splits(stats, seed=7)
    second = assign_channels_to_splits(stats, seed=7)
    assert first == second
