import numpy as np
import pandas as pd
import pytest

from sloppy.models.cv import ablate, cross_validate, make_folds, threshold_sweep

NUMERIC = ["signal", "noise"]


def _synthetic(n_channels: int = 20, per_channel: int = 10, down_channels: int = 6):
    """Channel-level labels, like the real corpus: every video in a channel shares its
    channel's label. `signal` is weakly label-related, `noise` is pure noise."""
    rng = np.random.default_rng(0)
    rows = []
    for c in range(n_channels):
        y = 1 if c < down_channels else 0
        for i in range(per_channel):
            rows.append(
                {
                    "video_id": f"v{c}_{i}",
                    "channel_id": f"c{c}",
                    "y": y,
                    "signal": y * 1.5 + rng.normal(),
                    "noise": rng.normal(),
                }
            )
    return pd.DataFrame(rows)


def _channels(df: pd.DataFrame, idx) -> set[str]:
    return set(df.iloc[idx]["channel_id"])


def test_group_by_channel_never_shares_a_channel_between_train_and_test():
    df = _synthetic()
    for train_idx, test_idx in make_folds(df, n_splits=5, seed=1, group_by="channel"):
        assert not (_channels(df, train_idx) & _channels(df, test_idx))


def test_every_video_is_tested_exactly_once_per_repeat():
    df = _synthetic()
    folds = make_folds(df, n_splits=5, seed=1, group_by="channel")
    tested = np.concatenate([test for _train, test in folds])
    assert sorted(tested) == list(range(len(df)))


def test_group_by_channel_stratifies_the_label_across_folds():
    df = _synthetic(n_channels=20, down_channels=6)
    for _train_idx, test_idx in make_folds(df, n_splits=3, seed=1, group_by="channel"):
        down_channels_in_fold = df.iloc[test_idx].query("y == 1")["channel_id"].nunique()
        # 6 down channels over 3 folds -> 2 each; allow one off for the greedy assignment
        assert 1 <= down_channels_in_fold <= 3


def test_group_by_video_does_share_channels_across_train_and_test():
    # The leaky variant exists on purpose, to measure the gap; make sure it really leaks.
    df = _synthetic()
    leaked = [
        _channels(df, train) & _channels(df, test)
        for train, test in make_folds(df, n_splits=5, seed=1, group_by="video")
    ]
    assert all(leaked)


def test_make_folds_is_deterministic_given_seed():
    df = _synthetic()
    first = make_folds(df, n_splits=5, seed=7, group_by="channel")
    second = make_folds(df, n_splits=5, seed=7, group_by="channel")
    assert all(np.array_equal(a[1], b[1]) for a, b in zip(first, second, strict=True))
    other = make_folds(df, n_splits=5, seed=8, group_by="channel")
    assert not all(np.array_equal(a[1], b[1]) for a, b in zip(first, other, strict=True))


def test_make_folds_rejects_too_few_channels_for_the_rarer_class():
    df = _synthetic(n_channels=10, down_channels=2)
    with pytest.raises(ValueError, match="rarer class has only 2 channel"):
        make_folds(df, n_splits=5, seed=1, group_by="channel")


def test_make_folds_rejects_bad_arguments():
    df = _synthetic()
    with pytest.raises(ValueError, match="group_by"):
        make_folds(df, n_splits=5, seed=1, group_by="nope")
    with pytest.raises(ValueError, match="n_splits"):
        make_folds(df, n_splits=1, seed=1, group_by="channel")


def test_cross_validate_collects_one_oof_score_per_video_and_summarizes():
    df = _synthetic()
    result = cross_validate(
        df, "logistic_regression", n_splits=4, numeric_features=NUMERIC, categorical_features=[]
    )
    assert len(result.folds) == 4
    assert len(result.oof) == len(df)
    assert set(result.oof["video_id"]) == set(df["video_id"])
    assert sum(f.n_test for f in result.folds) == len(df)

    summary = result.summary().set_index(["who", "metric"])
    assert 0.0 <= summary.loc[("model", "pr_auc"), "mean"] <= 1.0
    # signal is informative, so the model should beat the majority-class baseline's PR-AUC
    assert summary.loc[("model", "pr_auc"), "mean"] > summary.loc[("baseline", "pr_auc"), "mean"]
    assert result.pooled().n == len(df)


def test_cross_validate_repeats_multiply_folds_and_use_different_partitions():
    df = _synthetic()
    result = cross_validate(
        df,
        "logistic_regression",
        n_splits=4,
        repeats=2,
        numeric_features=NUMERIC,
        categorical_features=[],
    )
    assert len(result.folds) == 8
    assert {f.repeat for f in result.folds} == {0, 1}
    # pooled() counts each video once (first repeat only)
    assert result.pooled().n == len(df)
    first = result.oof[result.oof["repeat"] == 0].set_index("video_id")["fold"]
    second = result.oof[result.oof["repeat"] == 1].set_index("video_id")["fold"]
    assert not first.sort_index().equals(second.sort_index())


def test_ablate_shows_an_informative_group_beating_a_noise_only_group_on_paired_folds():
    df = _synthetic(n_channels=30, down_channels=10)
    table = ablate(
        df,
        "logistic_regression",
        n_splits=5,
        repeats=2,
        groups={"noise_only": (["noise"], []), "with_signal": (["noise", "signal"], [])},
    )

    assert list(table["feature_group"]) == ["noise_only", "with_signal"]
    assert list(table["n_features"]) == [1, 2]
    rows = table.set_index("feature_group")
    # the reference group's delta against itself is exactly zero
    assert rows.loc["noise_only", "pr_auc_vs_noise_only"] == 0.0
    assert rows.loc["with_signal", "pr_auc_vs_noise_only"] > 0.1
    assert rows.loc["with_signal", "pr_auc"] > rows.loc["noise_only", "pr_auc"]


def _oof(scores_and_labels, repeat=0):
    return pd.DataFrame([{"score": s, "y": y, "repeat": repeat} for s, y in scores_and_labels])


def test_threshold_sweep_computes_precision_recall_f1_per_threshold():
    # 4 slop videos (y=1) scored .9 .8 .4 .2, 4 fine videos (y=0) scored .7 .3 .2 .1
    oof = _oof([(0.9, 1), (0.8, 1), (0.4, 1), (0.2, 1), (0.7, 0), (0.3, 0), (0.2, 0), (0.1, 0)])

    sweep = threshold_sweep(oof, thresholds=(0.5, 0.3)).set_index("threshold")

    # at 0.5 flagged = {.9,.8,.7}: tp=2 fp=1 fn=2
    assert sweep.loc[0.5, "precision"] == pytest.approx(2 / 3)
    assert sweep.loc[0.5, "recall"] == pytest.approx(0.5)
    assert sweep.loc[0.5, "f1"] == pytest.approx(2 * 2 / (2 * 2 + 1 + 2))
    assert sweep.loc[0.5, "flagged"] == pytest.approx(3 / 8)
    # at 0.3 flagged = {.9,.8,.7,.4,.3}: tp=3 fp=2 fn=1
    assert sweep.loc[0.3, "precision"] == pytest.approx(3 / 5)
    assert sweep.loc[0.3, "recall"] == pytest.approx(3 / 4)


def test_threshold_sweep_averages_over_repeats_not_pooling_them():
    perfect = _oof([(0.9, 1), (0.1, 0)], repeat=0)  # f1 = 1 at threshold 0.5
    useless = _oof([(0.1, 1), (0.9, 0)], repeat=1)  # f1 = 0 at threshold 0.5

    sweep = threshold_sweep(pd.concat([perfect, useless]), thresholds=(0.5,))

    assert sweep.loc[0, "f1"] == pytest.approx(0.5)


def test_threshold_sweep_handles_a_threshold_that_flags_nothing():
    sweep = threshold_sweep(_oof([(0.2, 1), (0.1, 0)]), thresholds=(0.9,))
    assert np.isnan(sweep.loc[0, "precision"])
    assert sweep.loc[0, "f1"] == 0.0
    assert sweep.loc[0, "flagged"] == 0.0
