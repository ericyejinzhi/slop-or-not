"""Compute + persist NLP/vision features across many videos - extracted from the CLI's
compute-nlp/compute-vision commands (Phase 4) so Prefect tasks (Phase 7) can call the
same logic directly instead of duplicating it or shelling out to the CLI as a subprocess.

Both functions support an `only_missing` filter (videos that don't yet have a features
row) in addition to the CLI's original `video_id`/`limit` filters - a daily orchestrated
refresh should reprocess only what's new, not re-embed a channel's entire history every
run.
"""

import logging

import numpy as np
from sqlalchemy.orm import Session

from sloppy.config import Settings
from sloppy.db.models import Comment, Thumbnail, Video, VideoNlpFeatures, VideoVisionFeatures
from sloppy.db.session import session_scope
from sloppy.features.comment_topics import cluster_comment_topics
from sloppy.features.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL_NAME, embed_texts
from sloppy.features.nlp_store import upsert_video_nlp_features
from sloppy.features.sentiment import SENTIMENT_MODEL_NAME, aggregate_sentiment, score_comments
from sloppy.features.title_intent import score_title_intent
from sloppy.features.vision import (
    CLIP_MODEL_NAME,
    embed_image,
    load_thumbnail_image,
    zero_shot_scores,
)
from sloppy.features.vision_store import upsert_video_vision_features
from sloppy.storage import get_s3_client

logger = logging.getLogger(__name__)


def _select_videos_for_nlp(
    session: Session,
    video_id: str | None,
    limit: int | None,
    channel_id: str | None,
    only_missing: bool,
) -> list[Video]:
    query = session.query(Video)
    if video_id:
        query = query.filter(Video.id == video_id)
    if channel_id:
        query = query.filter(Video.channel_id == channel_id)
    if only_missing:
        query = query.outerjoin(VideoNlpFeatures, VideoNlpFeatures.video_id == Video.id).filter(
            VideoNlpFeatures.video_id.is_(None)
        )
    if limit:
        query = query.limit(limit)
    return query.all()


def compute_nlp_features(
    video_id: str | None = None,
    limit: int | None = None,
    channel_id: str | None = None,
    only_missing: bool = False,
) -> list[tuple[str, int]]:
    """Compute + persist sentiment/comment-topic/title-intent NLP features (including
    embeddings) for matching videos. Returns (video_id, comment_count_scored) pairs for
    every video actually processed. Idempotent - re-running overwrites.
    """
    with session_scope() as session:
        videos = _select_videos_for_nlp(session, video_id, limit, channel_id, only_missing)

    processed: list[tuple[str, int]] = []
    for video in videos:
        with session_scope() as session:
            comments = session.query(Comment).filter(Comment.video_id == video.id).all()
        texts = [c.text for c in comments]

        sentiment_scores = score_comments(texts)
        sentiment_agg = aggregate_sentiment(texts, sentiment_scores)

        comment_embeddings = embed_texts(texts) if texts else np.empty((0, EMBEDDING_DIM))
        comment_embedding_mean = comment_embeddings.mean(axis=0).tolist() if texts else None
        topic_agg = cluster_comment_topics(comment_embeddings, sentiment_scores)

        intent = score_title_intent(video.title)
        title_embedding = embed_texts([video.title])[0].tolist()
        description_embedding = (
            embed_texts([video.description])[0].tolist() if video.description else None
        )

        with session_scope() as session:
            upsert_video_nlp_features(
                session,
                video_id=video.id,
                comment_count_scored=sentiment_agg.comment_count_scored,
                sentiment_mean=sentiment_agg.sentiment_mean,
                sentiment_std=sentiment_agg.sentiment_std,
                sentiment_negative_share=sentiment_agg.sentiment_negative_share,
                slop_keyword_rate=sentiment_agg.slop_keyword_rate,
                topic_cluster_count=topic_agg.topic_cluster_count,
                topic_top_cluster_share=topic_agg.topic_top_cluster_share,
                topic_top_cluster_sentiment=topic_agg.topic_top_cluster_sentiment,
                topic_sentiment_spread=topic_agg.topic_sentiment_spread,
                title_lure_score=intent.lure_score,
                title_mysterious_score=intent.mysterious_score,
                title_transparent_score=intent.transparent_score,
                title_embedding=title_embedding,
                description_embedding=description_embedding,
                comment_embedding_mean=comment_embedding_mean,
                sentiment_model=SENTIMENT_MODEL_NAME,
                embedding_model=EMBEDDING_MODEL_NAME,
            )
        processed.append((video.id, len(texts)))

    return processed


def _select_videos_for_vision(
    session: Session,
    video_id: str | None,
    limit: int | None,
    channel_id: str | None,
    only_missing: bool,
) -> list[tuple[Video, Thumbnail]]:
    query = session.query(Video, Thumbnail).join(Thumbnail, Thumbnail.video_id == Video.id)
    if video_id:
        query = query.filter(Video.id == video_id)
    if channel_id:
        query = query.filter(Video.channel_id == channel_id)
    if only_missing:
        query = query.outerjoin(
            VideoVisionFeatures, VideoVisionFeatures.video_id == Video.id
        ).filter(VideoVisionFeatures.video_id.is_(None))
    if limit:
        query = query.limit(limit)
    return query.all()


def compute_vision_features(
    settings: Settings,
    video_id: str | None = None,
    limit: int | None = None,
    channel_id: str | None = None,
    only_missing: bool = False,
) -> list[str]:
    """Compute + persist CLIP thumbnail embeddings + zero-shot scores for matching
    videos that have a thumbnail on record. Returns the video ids actually processed - a
    bad thumbnail is logged and skipped, not raised. Idempotent - re-running overwrites.
    """
    s3_client = get_s3_client(settings)

    with session_scope() as session:
        rows = _select_videos_for_vision(session, video_id, limit, channel_id, only_missing)

    processed: list[str] = []
    for video, thumbnail in rows:
        try:
            image = load_thumbnail_image(s3_client, thumbnail.s3_bucket, thumbnail.s3_key)
            image_vec = embed_image(image)
            scores = zero_shot_scores(image)
        except Exception as exc:  # noqa: BLE001 - one bad thumbnail must not abort the run
            logger.warning("Failed to compute vision features for %s: %s", video.id, exc)
            continue

        with session_scope() as session:
            upsert_video_vision_features(
                session,
                video_id=video.id,
                image_embedding=image_vec.tolist(),
                clip_clickbait_score=scores["clip_clickbait_score"],
                clip_ai_generated_score=scores["clip_ai_generated_score"],
                clip_text_heavy_score=scores["clip_text_heavy_score"],
                clip_model=CLIP_MODEL_NAME,
            )
        processed.append(video.id)

    return processed
