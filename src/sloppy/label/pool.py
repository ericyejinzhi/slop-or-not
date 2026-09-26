"""Labeling pool selection.

Phase 1 ingestion pulls a channel's ENTIRE uploads history, but the roadmap's corpus-shape
rules (recent uploads only, >=15 and <=~30 per channel) are enforced here, at selection
time, not at ingestion time.
"""

import random
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sloppy.db.models import Channel, Label, Video


@dataclass
class PoolVideo:
    video_id: str
    channel_id: str
    channel_handle: str | None
    published_at: datetime


def candidate_videos(
    session: Session, per_channel_max: int = 30, exclude_labeled: bool = True
) -> list[PoolVideo]:
    """Per channel, its `per_channel_max` most-recently-published videos, optionally
    excluding any video that already has a label row (any label, including 'skip')."""
    row_number = (
        func.row_number()
        .over(partition_by=Video.channel_id, order_by=Video.published_at.desc())
        .label("rn")
    )
    ranked = select(
        Video.id.label("video_id"),
        Video.channel_id.label("channel_id"),
        Video.published_at.label("published_at"),
        row_number,
    ).subquery()

    stmt = select(ranked.c.video_id, ranked.c.channel_id, ranked.c.published_at).where(
        ranked.c.rn <= per_channel_max
    )
    if exclude_labeled:
        stmt = stmt.where(~select(Label.id).where(Label.video_id == ranked.c.video_id).exists())

    rows = session.execute(stmt).all()
    channel_handles = dict(session.execute(select(Channel.id, Channel.handle)).all())

    return [
        PoolVideo(
            video_id=row.video_id,
            channel_id=row.channel_id,
            channel_handle=channel_handles.get(row.channel_id),
            published_at=row.published_at,
        )
        for row in rows
    ]


def sample_pool(
    candidates: list[PoolVideo], target_size: int, seed: int | None = None
) -> list[PoolVideo]:
    """Seeded shuffle, truncated to target_size (or all, shuffled, if fewer exist)."""
    pool = list(candidates)
    random.Random(seed).shuffle(pool)
    return pool[:target_size]


def consistency_sample(session: Session, n: int = 20, seed: int | None = None) -> list[PoolVideo]:
    """Randomly sample `n` videos that already have a non-skip label, for the roadmap's
    consistency spot-check ("relabeling 20 videos a week later")."""
    labeled_video_ids = select(Label.video_id).where(Label.label != "skip").distinct()
    stmt = select(Video.id, Video.channel_id, Video.published_at).where(
        Video.id.in_(labeled_video_ids)
    )
    rows = session.execute(stmt).all()
    channel_handles = dict(session.execute(select(Channel.id, Channel.handle)).all())

    candidates = [
        PoolVideo(
            video_id=row.id,
            channel_id=row.channel_id,
            channel_handle=channel_handles.get(row.channel_id),
            published_at=row.published_at,
        )
        for row in rows
    ]
    random.Random(seed).shuffle(candidates)
    return candidates[:n]
