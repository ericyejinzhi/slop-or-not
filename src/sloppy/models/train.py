"""Baseline model training: logistic regression + XGBoost over engineered metadata
features (src/sloppy/features/). CPU-only - neither estimator is configured for GPU.
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

NUMERIC_FEATURES = [
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
]
CATEGORICAL_FEATURES = ["duration_bucket", "genre"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline([("impute", SimpleImputer(strategy="median"))])
    categorical_pipeline = Pipeline([("onehot", OneHotEncoder(handle_unknown="ignore"))])
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
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


def train_model(name: str, train_df: pd.DataFrame, version: str | None = None) -> TrainedModel:
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown model name {name!r}, expected one of {MODEL_NAMES}")

    pipeline = Pipeline(
        [("preprocess", build_preprocessor()), ("estimator", _build_estimator(name))]
    )
    pipeline.fit(train_df[ALL_FEATURES], train_df["y"])

    resolved_version = version or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return TrainedModel(name=name, version=resolved_version, pipeline=pipeline)


def save_model(trained: TrainedModel, artifacts_dir: Path, train_row_count: int) -> Path:
    model_dir = artifacts_dir / trained.name / trained.version
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.joblib"
    joblib.dump(trained.pipeline, model_path)

    metadata = {
        "model_name": trained.name,
        "model_version": trained.version,
        "features": ALL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "train_row_count": train_row_count,
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return model_path


def score_dataframe(trained: TrainedModel, df: pd.DataFrame) -> pd.Series:
    probabilities = trained.pipeline.predict_proba(df[ALL_FEATURES])
    down_index = list(trained.pipeline.classes_).index(1)
    return pd.Series(probabilities[:, down_index], index=df.index)
