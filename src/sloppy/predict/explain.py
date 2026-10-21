"""Why did the model give this score? Per-feature contributions for one prediction.

Positive contributions push toward "slop" (class 1, label "down"), negative ones away from
it. Units are log-odds, so they add up (with a bias term) to the model's raw output before
the final squashing into a probability. One-hot columns are folded back into the feature
they came from, so "genre" shows up once, not once per genre.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

# Plain-English names for the features a video-only model can use.
FEATURE_LABELS: dict[str, str] = {
    "title_caps_ratio": "Share of the title in capitals",
    "title_emoji_count": "Emoji in the title",
    "title_clickbait_score": "Clickbait wording in the title",
    "description_length": "Description length",
    "tag_count": "Number of tags",
    "like_view_ratio": "Likes per view",
    "comment_view_ratio": "Comments per view",
    "duration_seconds": "Video length",
    "duration_deviation_genre": "Length compared with similar videos",
    "title_curiosity_gap_count": "Curiosity-gap phrases in the title",
    "title_unresolved_pronoun_count": "Vague pronouns in the title",
    "title_all_caps_span_count": "ALL-CAPS words in the title",
    "title_ellipsis_count": "Ellipses in the title",
    "duration_bucket": "Length category",
    "genre": "Genre",
    "sentiment_mean": "Average comment sentiment",
    "sentiment_std": "Spread of comment sentiment",
    "sentiment_negative_share": "Share of negative comments",
    "slop_keyword_rate": "Comments that mention slop-like words",
    "topic_cluster_count": "Number of comment topics",
    "topic_top_cluster_share": "Share of comments in the biggest topic",
    "topic_top_cluster_sentiment": "Sentiment of the biggest comment topic",
    "topic_sentiment_spread": "Disagreement between comment topics",
    "title_lure_score": "How much the title lures",
    "title_mysterious_score": "How mysterious the title is",
    "title_transparent_score": "How transparent the title is",
    "mysterious_score_x_duration_bucket": "Mysterious title and video length",
    "lure_score_x_genre": "Lure level within its genre",
    "clip_clickbait_score": "Thumbnail looks clickbaity",
    "clip_ai_generated_score": "Thumbnail looks AI-generated",
    "clip_text_heavy_score": "Thumbnail is text-heavy",
    "near_duplicate_thumbnail_count": "Near-identical thumbnails in the dataset",
}


@dataclass
class FeatureContribution:
    feature: str
    label: str
    value: float | str | None
    contribution: float


def _source_feature(column: str, numeric: list[str], categorical: list[str]) -> str:
    """Map a fitted-pipeline output column back to the feature it came from."""
    name = column.split("__", 1)[-1]
    if name in numeric:
        return name
    matches = [f for f in categorical if name == f or name.startswith(f + "_")]
    return max(matches, key=len) if matches else name


def _python_value(value) -> float | str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    return None if (isinstance(value, float) and np.isnan(value)) else value


def explain_prediction(
    pipeline: Pipeline, row: pd.DataFrame, numeric: list[str], categorical: list[str]
) -> list[FeatureContribution]:
    """Contributions for the single row in `row`, strongest first. Returns [] for an
    estimator this does not know how to explain, so a prediction never fails on it."""
    preprocess = pipeline.named_steps["preprocess"]
    estimator = pipeline.named_steps["estimator"]

    matrix = preprocess.transform(row)
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    matrix = np.asarray(matrix, dtype=float)
    columns = list(preprocess.get_feature_names_out())

    if hasattr(estimator, "get_booster"):
        import xgboost as xgb

        per_column = estimator.get_booster().predict(xgb.DMatrix(matrix), pred_contribs=True)[0][
            :-1
        ]  # the last entry is the bias term
    elif hasattr(estimator, "coef_"):
        per_column = estimator.coef_[0] * matrix[0]
    else:
        return []

    totals: dict[str, float] = {}
    for column, contribution in zip(columns, per_column, strict=True):
        feature = _source_feature(column, numeric, categorical)
        totals[feature] = totals.get(feature, 0.0) + float(contribution)

    contributions = [
        FeatureContribution(
            feature=feature,
            label=FEATURE_LABELS.get(feature, feature),
            value=_python_value(row[feature].iloc[0]) if feature in row.columns else None,
            contribution=total,
        )
        for feature, total in totals.items()
    ]
    return sorted(contributions, key=lambda c: abs(c.contribution), reverse=True)
