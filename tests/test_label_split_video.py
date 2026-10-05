from sloppy.label.split import assign_videos_to_splits


def _canonical(n_channels: int = 10, per_channel: int = 10) -> dict[str, tuple[str, str]]:
    # Channel-level labels, like the real labeling scheme: every video in a channel shares
    # the channel's label (3 of every 10 channels are "down").
    return {
        f"v{c}_{i}": (f"c{c}", "down" if c % 10 < 3 else "up")
        for c in range(n_channels)
        for i in range(per_channel)
    }


def test_covers_every_video_once():
    canonical = _canonical()
    assignment = assign_videos_to_splits(canonical, seed=1)
    assert set(assignment) == set(canonical)
    assert set(assignment.values()) == {"train", "val", "test"}


def test_ignores_channels():
    # With channel-level labels, a channel's videos should (almost always) end up spread
    # over more than one split - the opposite of the channel-grouped guarantee.
    canonical = _canonical()
    assignment = assign_videos_to_splits(canonical, seed=1)
    splits_by_channel: dict[str, set[str]] = {}
    for vid, (cid, _label) in canonical.items():
        splits_by_channel.setdefault(cid, set()).add(assignment[vid])
    assert any(len(splits) > 1 for splits in splits_by_channel.values())


def test_stratifies_by_label_and_hits_proportions():
    canonical = _canonical(n_channels=20, per_channel=10)  # 200 videos
    assignment = assign_videos_to_splits(canonical, proportions=(0.70, 0.15, 0.15), seed=1)
    overall_down = sum(1 for _c, label in canonical.values() if label == "down") / len(canonical)
    for name, target in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        members = [v for v, split in assignment.items() if split == name]
        assert abs(len(members) / len(canonical) - target) < 0.03
        down = sum(1 for v in members if canonical[v][1] == "down") / len(members)
        assert abs(down - overall_down) < 0.05


def test_is_deterministic_given_seed():
    canonical = _canonical()
    assert assign_videos_to_splits(canonical, seed=7) == assign_videos_to_splits(canonical, seed=7)
    assert assign_videos_to_splits(canonical, seed=7) != assign_videos_to_splits(canonical, seed=8)
