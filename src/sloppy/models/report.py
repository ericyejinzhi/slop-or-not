"""Error-analysis report: the top-N most confidently wrong predictions, for the
"error-analysis notebook" the roadmap calls for - here as a CLI-testable report instead
(see docs/writeups/phase-3 for the rationale). A notebook can be layered on these same
functions later if still wanted.
"""

import pandas as pd


def top_errors(df: pd.DataFrame, kind: str, n: int = 20) -> pd.DataFrame:
    """kind: 'false_positive' (y=0, predicted down) or 'false_negative' (y=1, predicted
    up). df needs y, score, predicted_label columns (plus whatever else the caller wants
    to display - video_id, channel_id, title, etc. pass through untouched). Sorted by
    |score - 0.5| descending - most confidently wrong first."""
    if kind == "false_positive":
        errors = df[(df["y"] == 0) & (df["predicted_label"] == "down")]
    elif kind == "false_negative":
        errors = df[(df["y"] == 1) & (df["predicted_label"] == "up")]
    else:
        raise ValueError(f"kind must be 'false_positive' or 'false_negative', got {kind!r}")

    confidence = (errors["score"] - 0.5).abs()
    return (
        errors.assign(_confidence=confidence)
        .sort_values("_confidence", ascending=False)
        .drop(columns="_confidence")
        .head(n)
    )
