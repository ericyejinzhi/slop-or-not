"""Persisting CLIP vision features. Upsert on video_id alone, same rationale as
features/nlp_store.py.
"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sloppy.db.models import VideoVisionFeatures

_UPDATABLE_COLUMNS = (
    "image_embedding",
    "clip_clickbait_score",
    "clip_ai_generated_score",
    "clip_text_heavy_score",
    "clip_model",
)


def upsert_video_vision_features(session: Session, *, video_id: str, **fields) -> None:
    stmt = insert(VideoVisionFeatures).values(video_id=video_id, **fields)
    update_cols = {col: getattr(stmt.excluded, col) for col in _UPDATABLE_COLUMNS if col in fields}
    update_cols["updated_at"] = func.now()
    session.execute(stmt.on_conflict_do_update(index_elements=["video_id"], set_=update_cols))
