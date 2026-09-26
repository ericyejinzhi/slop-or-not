import json

import pandas as pd
from sklearn.metrics import roc_auc_score

from sloppy.models.train import ALL_FEATURES, save_model, score_dataframe, train_model


def _separable_dataframe(n: int = 200) -> pd.DataFrame:
    """A synthetic dataset where duration_deviation_channel alone perfectly predicts y -
    validates the training MACHINERY (does it fit, does scoring work), not real-world
    predictive power on actual YouTube data, which is impossible to test without real
    labels."""
    rows = []
    for i in range(n):
        is_down = i % 2 == 0
        rows.append(
            {
                "title_caps_ratio": 0.1,
                "title_emoji_count": 0,
                "title_clickbait_score": 0.0,
                "description_length": 100,
                "tag_count": 3,
                "like_view_ratio": 0.05,
                "comment_view_ratio": 0.01,
                "duration_seconds": 600,
                "duration_deviation_channel": 3.0 if is_down else -3.0,
                "duration_deviation_genre": 0.0,
                "channel_upload_cadence_days": 7.0,
                "duration_bucket": "mid",
                "genre": "Gaming" if i % 4 < 2 else "Cooking",
                "y": 1 if is_down else 0,
            }
        )
    return pd.DataFrame(rows)


def test_train_model_fits_and_separates_on_synthetic_data():
    df = _separable_dataframe()
    trained = train_model("logistic_regression", df, version="test-version")

    assert trained.name == "logistic_regression"
    assert trained.version == "test-version"

    scores = score_dataframe(trained, df)
    auc = roc_auc_score(df["y"], scores)
    assert auc > 0.9


def test_train_model_xgboost_fits_and_separates_on_synthetic_data():
    df = _separable_dataframe()
    trained = train_model("xgboost", df, version="test-version")
    scores = score_dataframe(trained, df)
    auc = roc_auc_score(df["y"], scores)
    assert auc > 0.9


def test_train_model_rejects_unknown_model_name():
    df = _separable_dataframe()
    try:
        train_model("not_a_real_model", df)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_train_model_version_defaults_to_a_timestamp_when_not_given():
    df = _separable_dataframe()
    trained = train_model("logistic_regression", df)
    assert len(trained.version) > 0


def test_save_model_writes_artifact_and_metadata(tmp_path):
    df = _separable_dataframe()
    trained = train_model("logistic_regression", df, version="test-version")

    model_path = save_model(trained, tmp_path, train_row_count=len(df))

    assert model_path.exists()
    assert model_path.name == "model.joblib"

    metadata_path = model_path.parent / "metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["model_name"] == "logistic_regression"
    assert metadata["model_version"] == "test-version"
    assert metadata["train_row_count"] == len(df)
    assert metadata["features"] == ALL_FEATURES
