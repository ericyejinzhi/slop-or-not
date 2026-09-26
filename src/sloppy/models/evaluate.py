"""Evaluation: PR-AUC, F1, confusion matrix, computed once per group so per-channel is a
byproduct of the same building block used for the overall metrics, not bolted on.
"""

from dataclasses import dataclass

import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score


@dataclass
class BinaryMetrics:
    n: int
    pr_auc: float
    f1: float
    tp: int
    fp: int
    tn: int
    fn: int


def _binary_metrics(y_true: pd.Series, y_score: pd.Series, threshold: float = 0.5) -> BinaryMetrics:
    y_pred = (y_score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    # average_precision_score needs both classes present to be meaningful; a
    # single-class group (e.g. a small/leaky channel) can't compute a real PR-AUC.
    pr_auc = average_precision_score(y_true, y_score) if y_true.nunique() > 1 else float("nan")
    return BinaryMetrics(
        n=len(y_true),
        pr_auc=pr_auc,
        f1=f1_score(y_true, y_pred, zero_division=0),
        tp=int(tp),
        fp=int(fp),
        tn=int(tn),
        fn=int(fn),
    )


def majority_class_baseline(train_y: pd.Series) -> str:
    """The mode of y in the TRAIN split only (never val/test) - 'up' (0) or 'down' (1)."""
    mode_value = train_y.mode().iloc[0]
    return "down" if mode_value == 1 else "up"


@dataclass
class EvaluationReport:
    overall: BinaryMetrics
    majority_baseline: BinaryMetrics
    per_channel: dict[str, BinaryMetrics]


def evaluate(
    df: pd.DataFrame, train_y: pd.Series, y_col: str = "y", score_col: str = "score"
) -> EvaluationReport:
    """`df` should already be filtered to one split (e.g. val or test) by the caller, and
    must have channel_id/y/score columns. `train_y` is the TRAIN split's y column, used
    only to compute the majority-class baseline (never the eval split's own labels)."""
    overall = _binary_metrics(df[y_col], df[score_col])

    baseline_label = majority_class_baseline(train_y)
    baseline_score = pd.Series(1.0 if baseline_label == "down" else 0.0, index=df.index)
    baseline = _binary_metrics(df[y_col], baseline_score)

    per_channel = {
        channel_id: _binary_metrics(group[y_col], group[score_col])
        for channel_id, group in df.groupby("channel_id")
    }

    return EvaluationReport(overall=overall, majority_baseline=baseline, per_channel=per_channel)
