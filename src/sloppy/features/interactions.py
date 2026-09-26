"""Explicit feature crosses from the roadmap: XGBoost learns interactions natively, but
seeding it with explicit crosses where we know the story helps. Pure, no ML - these are
simple products/concatenations of already-computed feature columns.
"""

LURE_HIGH_THRESHOLD = 0.5
DURATION_BUCKET_ORDINAL = {"short": 0, "mid": 1, "long": 2, "unknown": None}


def lure_score_x_genre(title_lure_score: float | None, genre: str) -> str | None:
    """Genre is nominal (no natural order), so this cross is a categorical
    concatenation fed through the existing OneHotEncoder pipeline, not a numeric
    product."""
    if title_lure_score is None:
        return None
    bucket = "high" if title_lure_score >= LURE_HIGH_THRESHOLD else "low"
    return f"{genre}::{bucket}"


def duration_deviation_x_cadence(
    duration_deviation_genre: float | None, cadence_days: float | None
) -> float | None:
    if duration_deviation_genre is None or cadence_days is None:
        return None
    return duration_deviation_genre * cadence_days


def mysterious_score_x_duration_bucket(
    title_mysterious_score: float | None, duration_bucket: str
) -> float | None:
    """duration_bucket IS ordinal (short<mid<long), unlike genre, so this cross is a
    numeric product using DURATION_BUCKET_ORDINAL."""
    ordinal = DURATION_BUCKET_ORDINAL.get(duration_bucket)
    if title_mysterious_score is None or ordinal is None:
        return None
    return title_mysterious_score * ordinal
