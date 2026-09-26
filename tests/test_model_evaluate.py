import pandas as pd

from sloppy.models.evaluate import BinaryMetrics, evaluate, majority_class_baseline


def test_majority_class_baseline_picks_the_mode():
    train_y = pd.Series([1, 1, 1, 0, 0])
    assert majority_class_baseline(train_y) == "down"

    train_y = pd.Series([0, 0, 0, 1])
    assert majority_class_baseline(train_y) == "up"


def test_evaluate_perfect_separation_scores_well():
    df = pd.DataFrame(
        {
            "channel_id": ["c1"] * 10,
            "y": [1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
            "score": [0.9, 0.95, 0.99, 0.85, 0.92, 0.1, 0.05, 0.2, 0.15, 0.02],
        }
    )
    train_y = pd.Series([1, 0, 1, 0, 1])  # balanced train set for a neutral baseline
    report = evaluate(df, train_y)

    assert report.overall.f1 == 1.0
    assert report.overall.pr_auc == 1.0
    assert report.overall.fp == 0
    assert report.overall.fn == 0


def test_evaluate_degenerate_majority_baseline_case():
    # train set is 90% one class - the baseline should reflect that skew
    train_y = pd.Series([1] * 9 + [0])
    df = pd.DataFrame(
        {
            "channel_id": ["c1"] * 4,
            "y": [1, 1, 0, 0],
            "score": [0.9, 0.8, 0.3, 0.2],
        }
    )
    report = evaluate(df, train_y)
    # majority baseline predicts "down" (1) for everyone - 2 true positives, 2 false
    # positives, 0 true negatives, 0 false negatives
    assert report.majority_baseline.tp == 2
    assert report.majority_baseline.fp == 2
    assert report.majority_baseline.tn == 0
    assert report.majority_baseline.fn == 0


def test_evaluate_per_channel_surfaces_a_leaky_channel():
    # channel "leaky" has suspiciously perfect separation while "normal" doesn't -
    # per-channel output should make this visible rather than averaging it away.
    df = pd.DataFrame(
        {
            "channel_id": ["leaky"] * 4 + ["normal"] * 4,
            "y": [1, 1, 0, 0, 1, 0, 1, 0],
            "score": [0.99, 0.98, 0.01, 0.02, 0.6, 0.55, 0.45, 0.5],
        }
    )
    train_y = pd.Series([1, 0, 1, 0])
    report = evaluate(df, train_y)

    assert report.per_channel["leaky"].f1 == 1.0
    assert report.per_channel["normal"].f1 < 1.0


def test_binary_metrics_handles_single_class_group_pr_auc_as_nan():
    from sloppy.models.evaluate import _binary_metrics

    y_true = pd.Series([1, 1, 1])
    y_score = pd.Series([0.9, 0.8, 0.7])
    metrics: BinaryMetrics = _binary_metrics(y_true, y_score)
    assert pd.isna(metrics.pr_auc)
