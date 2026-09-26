"""Baseline model training: logistic regression + XGBoost over engineered features
(src/sloppy/features/). CPU-only - neither estimator is configured for GPU.

Features are organized into 3 cumulative groups (metadata / metadata+text / all) so
Stage 13's ablation can train the same estimator on each group via the same
train_model/build_preprocessor/score_dataframe functions - no duplicated training logic.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

MODEL_NAMES = ("logistic_regression", "xgboost")

METADATA_NUMERIC_FEATURES = [
    "title_caps_ratio",
    "title_emoji_count",
    "title_clickbait_score",
    "description_length",
    "tag_count",
    "like_view_ratio",
    "comment_view_ratio",
    "duration_seconds",
    "duration_deviation_channel",
    "duration_deviation_genre",
    "channel_upload_cadence_days",
    "title_curiosity_gap_count",
    "title_unresolved_pronoun_count",
    "title_all_caps_span_count",
    "title_ellipsis_count",
]
METADATA_CATEGORICAL_FEATURES = ["duration_bucket", "genre"]

# "Text" = anything derived from sentence-transformers/sentiment/title-intent (Stages
# 5-7, 11) - includes the two interactions that depend on a text-derived score, and the
# title-embedding similarity feature (it comes from video_nlp_features, not vision).
TEXT_NUMERIC_FEATURES = [
    "sentiment_mean",
    "sentiment_std",
    "sentiment_negative_share",
    "slop_keyword_rate",
    "topic_cluster_count",
    "topic_top_cluster_share",
    "topic_top_cluster_sentiment",
    "topic_sentiment_spread",
    "title_lure_score",
    "title_mysterious_score",
    "title_transparent_score",
    "channel_sentiment_mean",
    "channel_title_self_similarity",
    "duration_deviation_x_cadence",
    "mysterious_score_x_duration_bucket",
]
TEXT_CATEGORICAL_FEATURES = ["lure_score_x_genre"]

# "Vision" = CLIP-derived (Stages 8-10).
VISION_NUMERIC_FEATURES = [
    "clip_clickbait_score",
    "clip_ai_generated_score",
    "clip_text_heavy_score",
    "channel_thumbnail_self_similarity",
    "near_duplicate_thumbnail_count",
]
VISION_CATEGORICAL_FEATURES: list[str] = []

FEATURE_GROUPS: dict[str, tuple[list[str], list[str]]] = {
    "metadata": (METADATA_NUMERIC_FEATURES, METADATA_CATEGORICAL_FEATURES),
    "metadata_text": (
        METADATA_NUMERIC_FEATURES + TEXT_NUMERIC_FEATURES,
        METADATA_CATEGORICAL_FEATURES + TEXT_CATEGORICAL_FEATURES,
    ),
    "all": (
        METADATA_NUMERIC_FEATURES + TEXT_NUMERIC_FEATURES + VISION_NUMERIC_FEATURES,
        METADATA_CATEGORICAL_FEATURES + TEXT_CATEGORICAL_FEATURES + VISION_CATEGORICAL_FEATURES,
    ),
}

# Default feature set for plain (non-ablation) training - the full "all" group.
NUMERIC_FEATURES, CATEGORICAL_FEATURES = FEATURE_GROUPS["all"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def build_preprocessor(
    numeric_features: list[str], categorical_features: list[str]
) -> ColumnTransformer:
    numeric_pipeline = Pipeline([("impute", SimpleImputer(strategy="median"))])
    categorical_pipeline = Pipeline([("onehot", OneHotEncoder(handle_unknown="ignore"))])
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric_features),
            ("categorical", categorical_pipeline, categorical_features),
        ]
    )


def _build_estimator(name: str):
    if name == "logistic_regression":
        return LogisticRegression(max_iter=1000, class_weight="balanced")
    if name == "xgboost":
        return XGBClassifier(n_estimators=200, max_depth=4, n_jobs=-1)
    raise ValueError(f"Unknown model name {name!r}, expected one of {MODEL_NAMES}")


@dataclass
class TrainedModel:
    name: str
    version: str
    pipeline: Pipeline
    numeric_features: list[str]
    categorical_features: list[str]

    @property
    def all_features(self) -> list[str]:
        return self.numeric_features + self.categorical_features


def train_model(
    name: str,
    train_df: pd.DataFrame,
    numeric_features: list[str] | None = None,
    categorical_features: list[str] | None = None,
    version: str | None = None,
) -> TrainedModel:
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown model name {name!r}, expected one of {MODEL_NAMES}")

    numeric_features = numeric_features if numeric_features is not None else NUMERIC_FEATURES
    categorical_features = (
        categorical_features if categorical_features is not None else CATEGORICAL_FEATURES
    )

    pipeline = Pipeline(
        [
            ("preprocess", build_preprocessor(numeric_features, categorical_features)),
            ("estimator", _build_estimator(name)),
        ]
    )
    pipeline.fit(train_df[numeric_features + categorical_features], train_df["y"])

    resolved_version = version or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return TrainedModel(
        name=name,
        version=resolved_version,
        pipeline=pipeline,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
    )


def save_model(trained: TrainedModel, artifacts_dir: Path, train_row_count: int) -> Path:
    model_dir = artifacts_dir / trained.name / trained.version
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.joblib"
    joblib.dump(trained.pipeline, model_path)

    metadata = {
        "model_name": trained.name,
        "model_version": trained.version,
        "features": trained.all_features,
        "numeric_features": trained.numeric_features,
        "categorical_features": trained.categorical_features,
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "train_row_count": train_row_count,
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return model_path


def score_dataframe(trained: TrainedModel, df: pd.DataFrame) -> pd.Series:
    probabilities = trained.pipeline.predict_proba(df[trained.all_features])
    down_index = list(trained.pipeline.classes_).index(1)
    return pd.Series(probabilities[:, down_index], index=df.index)
