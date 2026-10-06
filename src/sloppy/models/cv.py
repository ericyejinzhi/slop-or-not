"""Stratified k-fold cross-validation, grouped by channel by default.

Labels are per channel (every video in a channel shares one label), so a plain
stratified-by-video k-fold would put a channel in both the training and held-out folds and
let the model score well just by recognizing the channel. `StratifiedGroupKFold` with
channel_id as the group keeps each channel entirely inside one fold while still balancing
the up/down ratio across folds. `group_by="video"` (plain `StratifiedKFold`) is kept only
so the leakage gap can be measured directly against the grouped number.

Works on an already-assembled dataframe (channel_id/y/features), so it needs no database;
training and metrics reuse train.py's train_model/score_dataframe and evaluate.py.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from sloppy.models.evaluate import BinaryMetrics, EvaluationReport, _binary_metrics, evaluate
from sloppy.models.train import score_dataframe, train_model

GROUP_BY_CHOICES = ("channel", "video")


@dataclass
class FoldResult:
    repeat: int
    fold: int
    n_train: int
    n_test: int
    n_test_channels: int
    report: EvaluationReport


@dataclass
class CrossValidationResult:
    model_name: str
    group_by: str
    folds: list[FoldResult]
    # One out-of-fold prediction per video per repeat: every labeled video is scored by a
    # model that never saw it (or, under group_by="channel", its channel) in training.
    oof: pd.DataFrame

    def pooled(self) -> BinaryMetrics:
        """Metrics over all out-of-fold predictions at once (first repeat only, so each
        video counts once)."""
        first = self.oof[self.oof["repeat"] == 0]
        return _binary_metrics(first["y"], first["score"])

    def summary(self) -> pd.DataFrame:
        """Mean and standard deviation across folds (all repeats) of each headline metric,
        for the model and for the majority-class baseline."""
        rows = []
        for name, getter in (
            ("model", lambda f: f.report.overall),
            ("baseline", lambda f: f.report.majority_baseline),
        ):
            for metric in ("pr_auc", "f1"):
                values = np.array([getattr(getter(f), metric) for f in self.folds], dtype=float)
                rows.append(
                    {
                        "who": name,
                        "metric": metric,
                        "mean": float(np.nanmean(values)),
                        "std": float(np.nanstd(values)),
                        "min": float(np.nanmin(values)),
                        "max": float(np.nanmax(values)),
                    }
                )
        return pd.DataFrame(rows)


def make_folds(
    df: pd.DataFrame, n_splits: int, seed: int, group_by: str
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Positional (train_idx, test_idx) pairs. `df` needs `y` and, for group_by="channel",
    `channel_id`. Raises ValueError up front if there are too few channels (or too few
    members of a class) for the requested number of folds, instead of letting sklearn
    quietly produce lopsided or empty folds."""
    if group_by not in GROUP_BY_CHOICES:
        raise ValueError(f"group_by must be one of {GROUP_BY_CHOICES}, got {group_by!r}")
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    y = df["y"].to_numpy()
    if group_by == "channel":
        groups = df["channel_id"].to_numpy()
        # Labels are channel-level, so a class needs at least n_splits channels to appear
        # in every fold; check on channels, not videos.
        channels_per_class = df.groupby("y")["channel_id"].nunique()
        if len(channels_per_class) < 2:
            raise ValueError("Need both classes (up and down) to cross-validate")
        if channels_per_class.min() < n_splits:
            raise ValueError(
                f"The rarer class has only {channels_per_class.min()} channel(s), fewer than "
                f"n_splits={n_splits}; lower --folds."
            )
        splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        return list(splitter.split(np.zeros(len(df)), y, groups))

    if pd.Series(y).value_counts().min() < n_splits:
        raise ValueError(f"The rarer class has fewer than n_splits={n_splits} videos")
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(splitter.split(np.zeros(len(df)), y))


def cross_validate(
    df: pd.DataFrame,
    model_name: str,
    n_splits: int = 5,
    seed: int = 42,
    repeats: int = 1,
    group_by: str = "channel",
    numeric_features: list[str] | None = None,
    categorical_features: list[str] | None = None,
) -> CrossValidationResult:
    """`df` must have `video_id`, `channel_id`, `y` and the feature columns (as returned by
    features.dataset.assemble_dataset). Repeat r uses seed + r, so repeats see different
    partitions of the channels."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    df = df.reset_index(drop=True)

    folds: list[FoldResult] = []
    oof_parts: list[pd.DataFrame] = []

    for repeat in range(repeats):
        for fold_number, (train_idx, test_idx) in enumerate(
            make_folds(df, n_splits, seed + repeat, group_by)
        ):
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx].copy()

            trained = train_model(
                model_name,
                train_df,
                numeric_features=numeric_features,
                categorical_features=categorical_features,
            )
            test_df["score"] = score_dataframe(trained, test_df)

            folds.append(
                FoldResult(
                    repeat=repeat,
                    fold=fold_number,
                    n_train=len(train_df),
                    n_test=len(test_df),
                    n_test_channels=test_df["channel_id"].nunique(),
                    report=evaluate(test_df, train_df["y"]),
                )
            )
            part = test_df[["video_id", "channel_id", "y", "score"]].copy()
            part["repeat"] = repeat
            part["fold"] = fold_number
            oof_parts.append(part)

    return CrossValidationResult(
        model_name=model_name,
        group_by=group_by,
        folds=folds,
        oof=pd.concat(oof_parts, ignore_index=True),
    )
