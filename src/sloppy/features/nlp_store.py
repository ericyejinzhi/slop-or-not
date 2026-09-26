"""Persisting NLP feature aggregates + embeddings. Upsert on video_id alone (not a
composite key like video_scores) - see VideoNlpFeatures' docstring for why.
"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sloppy.db.models import VideoNlpFeatures

_UPDATABLE_COLUMNS = (
    "comment_count_scored",
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
    "title_embedding",
    "description_embedding",
    "comment_embedding_mean",
    "sentiment_model",
    "embedding_model",
)


def upsert_video_nlp_features(session: Session, *, video_id: str, **fields) -> None:
    stmt = insert(VideoNlpFeatures).values(video_id=video_id, **fields)
    update_cols = {col: getattr(stmt.excluded, col) for col in _UPDATABLE_COLUMNS if col in fields}
    update_cols["updated_at"] = func.now()
    session.execute(stmt.on_conflict_do_update(index_elements=["video_id"], set_=update_cols))
