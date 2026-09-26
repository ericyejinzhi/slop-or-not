from sloppy.features.interactions import (
    duration_deviation_x_cadence,
    lure_score_x_genre,
    mysterious_score_x_duration_bucket,
)


def test_lure_score_x_genre_high_and_low():
    assert lure_score_x_genre(0.8, "Gaming") == "Gaming::high"
    assert lure_score_x_genre(0.3, "Gaming") == "Gaming::low"
    assert lure_score_x_genre(0.5, "Cooking") == "Cooking::high"  # boundary is inclusive


def test_lure_score_x_genre_none_when_score_missing():
    assert lure_score_x_genre(None, "Gaming") is None


def test_duration_deviation_x_cadence_multiplies():
    assert duration_deviation_x_cadence(2.0, 3.0) == 6.0
    assert duration_deviation_x_cadence(-1.5, 4.0) == -6.0


def test_duration_deviation_x_cadence_none_when_either_missing():
    assert duration_deviation_x_cadence(None, 3.0) is None
    assert duration_deviation_x_cadence(2.0, None) is None
    assert duration_deviation_x_cadence(None, None) is None


def test_mysterious_score_x_duration_bucket_uses_ordinal():
    assert mysterious_score_x_duration_bucket(0.5, "short") == 0.0  # ordinal 0
    assert mysterious_score_x_duration_bucket(0.5, "mid") == 0.5  # ordinal 1
    assert mysterious_score_x_duration_bucket(0.5, "long") == 1.0  # ordinal 2


def test_mysterious_score_x_duration_bucket_none_for_unknown_bucket():
    assert mysterious_score_x_duration_bucket(0.5, "unknown") is None


def test_mysterious_score_x_duration_bucket_none_when_score_missing():
    assert mysterious_score_x_duration_bucket(None, "mid") is None
