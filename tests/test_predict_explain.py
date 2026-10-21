"""Per-feature contributions, checked against models trained on a toy problem where the
answer is known: only `signal` matters, `noise` does not."""

import numpy as np
import pandas as pd
import pytest

from sloppy.models.train import train_model
from sloppy.predict.explain import explain_prediction

NUMERIC = ["signal", "noise"]
CATEGORICAL = ["genre"]


def _toy_frame(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    signal = rng.normal(size=n)
    return pd.DataFrame(
        {
            "signal": signal,
            "noise": rng.normal(size=n),
            "genre": rng.choice(["Music", "Gaming"], size=n),
            "y": (signal > 0).astype(int),
        }
    )


def _row(signal: float) -> pd.DataFrame:
    return pd.DataFrame([{"signal": signal, "noise": 0.0, "genre": "Music"}])


@pytest.mark.parametrize("model_name", ["logistic_regression", "xgboost"])
def test_the_feature_that_drives_the_label_dominates_and_points_the_right_way(model_name):
    trained = train_model(model_name, _toy_frame(), NUMERIC, CATEGORICAL)

    high = explain_prediction(trained.pipeline, _row(2.5), NUMERIC, CATEGORICAL)
    low = explain_prediction(trained.pipeline, _row(-2.5), NUMERIC, CATEGORICAL)

    assert high[0].feature == "signal"
    assert high[0].contribution > 0  # toward slop (class 1)
    assert low[0].feature == "signal"
    assert low[0].contribution < 0
    assert high[0].label  # every entry carries a readable label
    assert high[0].value == 2.5


@pytest.mark.parametrize("model_name", ["logistic_regression", "xgboost"])
def test_one_hot_columns_are_folded_back_into_their_feature(model_name):
    trained = train_model(model_name, _toy_frame(), NUMERIC, CATEGORICAL)

    explained = explain_prediction(trained.pipeline, _row(1.0), NUMERIC, CATEGORICAL)

    names = [c.feature for c in explained]
    assert sorted(names) == ["genre", "noise", "signal"]  # not genre_Music / genre_Gaming
    assert len(names) == len(set(names))


def test_logistic_contributions_add_up_to_the_models_log_odds():
    trained = train_model("logistic_regression", _toy_frame(), NUMERIC, CATEGORICAL)
    row = _row(1.2)

    explained = explain_prediction(trained.pipeline, row, NUMERIC, CATEGORICAL)

    estimator = trained.pipeline.named_steps["estimator"]
    log_odds = float(trained.pipeline.decision_function(row)[0])
    assert sum(c.contribution for c in explained) + float(estimator.intercept_[0]) == pytest.approx(
        log_odds
    )


def test_missing_values_are_reported_as_none_not_nan():
    trained = train_model("logistic_regression", _toy_frame(), NUMERIC, CATEGORICAL)
    row = pd.DataFrame([{"signal": np.nan, "noise": 0.0, "genre": "Music"}])

    explained = explain_prediction(trained.pipeline, row, NUMERIC, CATEGORICAL)

    assert next(c for c in explained if c.feature == "signal").value is None
