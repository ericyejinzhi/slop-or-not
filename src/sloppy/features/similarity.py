"""Cross-video similarity features, computed at dataset-assembly time via pgvector
cosine-distance queries - NOT persisted (no new table), same pattern as
features/corpus.py's stats being rebuilt fresh every run. Uses the `<=>` operator
directly via raw SQL/text() - querying doesn't need the ORM Vector type, only the
column definition does.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

# Judgment call, flagged as revisit-after-real-data: how close two thumbnails' cosine
# distance must be to count as "near-duplicate."
NEAR_DUPLICATE_COSINE_DISTANCE = 0.05


def channel_thumbnail_self_similarity_mean(
    session: Session, video_id: str, channel_id: str
) -> float | None:
    """Mean pgvector cosine distance between this video's image_embedding and every
    other video in its channel - the "templated-ness" signal. None if this video has no
    embedding, or no other channel video has one to compare against."""
    result = session.execute(
        text("""
            SELECT AVG(other.image_embedding <=> mine.image_embedding)
            FROM video_vision_features mine
            JOIN videos v ON v.id = mine.video_id
            JOIN video_vision_features other ON other.video_id != mine.video_id
            JOIN videos ov ON ov.id = other.video_id AND ov.channel_id = :channel_id
            WHERE mine.video_id = :video_id
        """),
        {"video_id": video_id, "channel_id": channel_id},
    ).scalar()
    return float(result) if result is not None else None


def near_duplicate_thumbnail_count(session: Session, video_id: str) -> int | None:
    """Corpus-wide (not channel-scoped) count of thumbnails within
    NEAR_DUPLICATE_COSINE_DISTANCE of this one. None if this video has no embedding."""
    has_embedding = session.execute(
        text("SELECT 1 FROM video_vision_features WHERE video_id = :video_id"),
        {"video_id": video_id},
    ).scalar()
    if has_embedding is None:
        return None

    result = session.execute(
        text("""
            SELECT count(*)
            FROM video_vision_features other
            JOIN video_vision_features mine ON mine.video_id = :video_id
            WHERE other.video_id != :video_id
              AND other.image_embedding <=> mine.image_embedding < :threshold
        """),
        {"video_id": video_id, "threshold": NEAR_DUPLICATE_COSINE_DISTANCE},
    ).scalar()
    return int(result)


def channel_title_self_similarity_mean(
    session: Session, video_id: str, channel_id: str
) -> float | None:
    """Same as channel_thumbnail_self_similarity_mean, but for title_embedding - a
    text-templated-ness signal, symmetric to the thumbnail one."""
    result = session.execute(
        text("""
            SELECT AVG(other.title_embedding <=> mine.title_embedding)
            FROM video_nlp_features mine
            JOIN videos v ON v.id = mine.video_id
            JOIN video_nlp_features other ON other.video_id != mine.video_id
            JOIN videos ov ON ov.id = other.video_id AND ov.channel_id = :channel_id
            WHERE mine.video_id = :video_id
        """),
        {"video_id": video_id, "channel_id": channel_id},
    ).scalar()
    return float(result) if result is not None else None
