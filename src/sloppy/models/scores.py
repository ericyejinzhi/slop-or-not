"""Persisting model predictions. Upsert (not append-only, unlike labels) - a score is a
reproducible function of a specific model version scoring a specific video; re-scoring
with the SAME model version overwrites, while different model names/versions coexist.
"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sloppy.db.models import VideoScore


def upsert_video_score(
    session: Session,
    *,
    video_id: str,
    model_name: str,
    model_version: str,
    score: float,
    predicted_label: str,
    split: str,
) -> None:
    stmt = insert(VideoScore).values(
        video_id=video_id,
        model_name=model_name,
        model_version=model_version,
        score=score,
        predicted_label=predicted_label,
        split=split,
    )
    update_cols = {
        "score": stmt.excluded.score,
        "predicted_label": stmt.excluded.predicted_label,
        "split": stmt.excluded.split,
        "updated_at": func.now(),
    }
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["video_id", "model_name", "model_version"], set_=update_cols
        )
    )
