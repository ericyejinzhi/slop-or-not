import pandas as pd

from sloppy.models.report import top_errors


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "video_id": ["v1", "v2", "v3", "v4", "v5"],
            "y": [0, 0, 1, 1, 0],
            "predicted_label": ["down", "up", "up", "down", "down"],
            "score": [0.95, 0.4, 0.1, 0.6, 0.55],
        }
    )


def test_top_errors_false_positive_filters_correctly():
    # false positives: y=0 but predicted "down" -> v1 (score 0.95) and v5 (score 0.55)
    result = top_errors(_sample_df(), "false_positive", n=10)
    assert set(result["video_id"]) == {"v1", "v5"}


def test_top_errors_false_negative_filters_correctly():
    # false negatives: y=1 but predicted "up" -> v3 (score 0.1)
    result = top_errors(_sample_df(), "false_negative", n=10)
    assert set(result["video_id"]) == {"v3"}


def test_top_errors_sorted_by_confidence_descending():
    result = top_errors(_sample_df(), "false_positive", n=10)
    # v1 (score 0.95, |0.95-0.5|=0.45) is more confidently wrong than v5 (0.55, |0.05|)
    assert list(result["video_id"]) == ["v1", "v5"]


def test_top_errors_respects_n_limit():
    result = top_errors(_sample_df(), "false_positive", n=1)
    assert len(result) == 1
    assert result.iloc[0]["video_id"] == "v1"


def test_top_errors_invalid_kind_raises():
    try:
        top_errors(_sample_df(), "not_a_kind")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_top_errors_empty_when_no_errors_of_that_kind():
    df = pd.DataFrame(
        {
            "video_id": ["v1"],
            "y": [1],
            "predicted_label": ["down"],
            "score": [0.9],
        }
    )
    result = top_errors(df, "false_positive", n=10)
    assert result.empty
