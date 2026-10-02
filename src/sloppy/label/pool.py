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


@dataclass
class ChannelBatch:
    channel_id: str
    channel_handle: str | None
    videos: list[PoolVideo]


def candidate_channel_batches(session: Session, exclude_labeled: bool = True) -> list[ChannelBatch]:
    """Groups every ingested video by channel, for channel-batch labeling - the current
    primary labeling methodology (see docs/writeups/TODO.md). No per-channel cap is
    applied here (unlike `candidate_videos`): channels are already sampled down to a
    small, fixed size at ingest/trim time, so every video a channel has IS its batch.

    `exclude_labeled=True` drops a channel entirely once ANY of its videos has a label
    row - mirroring `candidate_videos`'s own "any label" exclusion semantics at the
    channel level, since a channel-batch label is applied to the whole batch atomically
    (see `sloppy.api.routers.labels.create_batch_label`), so "partially labeled" isn't a
    normal state to design around.
    """
    stmt = select(Video.id, Video.channel_id, Video.published_at)
    if exclude_labeled:
        labeled_channel_ids = (
            select(Video.channel_id).join(Label, Label.video_id == Video.id).distinct()
        )
        stmt = stmt.where(~Video.channel_id.in_(labeled_channel_ids))

    rows = session.execute(stmt).all()
    channel_handles = dict(session.execute(select(Channel.id, Channel.handle)).all())

    grouped: dict[str, list[PoolVideo]] = {}
    for row in rows:
        grouped.setdefault(row.channel_id, []).append(
            PoolVideo(
                video_id=row.id,
                channel_id=row.channel_id,
                channel_handle=channel_handles.get(row.channel_id),
                published_at=row.published_at,
            )
        )

    return [
        ChannelBatch(
            channel_id=channel_id,
            channel_handle=channel_handles.get(channel_id),
            videos=videos,
        )
        for channel_id, videos in grouped.items()
    ]


def sample_channel_batches(
    batches: list[ChannelBatch], target_size: int, seed: int | None = None
) -> list[ChannelBatch]:
    """Seeded shuffle, truncated to target_size (or all, shuffled, if fewer exist) -
    same shape as `sample_pool`, just operating on whole channel batches."""
    pool = list(batches)
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
