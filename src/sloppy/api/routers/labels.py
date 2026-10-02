from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sloppy.api.dependencies import get_db, get_s3
from sloppy.api.schemas import (
    BatchLabelCreateRequest,
    BatchLabelResponse,
    ChannelBatchPoolItem,
    ChannelBatchPoolResponse,
    LabelCreateRequest,
    LabeledVideoItem,
    LabeledVideoListResponse,
    LabelPoolItem,
    LabelPoolResponse,
    LabelResponse,
)
from sloppy.api.thumbnails import presigned_thumbnail_url
from sloppy.config import get_settings
from sloppy.db.models import Channel, Label, Thumbnail, Video
from sloppy.label.labels import record_label
from sloppy.label.pool import (
    PoolVideo,
    candidate_channel_batches,
    candidate_videos,
    consistency_sample,
    sample_channel_batches,
    sample_pool,
)

labels_router = APIRouter(prefix="/labels", tags=["labels"])


def _pool_items_for(
    session: Session, s3_client, pool_videos: list[PoolVideo]
) -> list[LabelPoolItem]:
    """Shared by GET /labels/pool and GET /labels/channel-pool - both need to turn a list
    of PoolVideo (just ids + channel metadata) into the full LabelPoolItem shape (title,
    stats, presigned thumbnail) the frontend actually renders."""
    video_ids = [p.video_id for p in pool_videos]
    videos = {
        v.id: v for v in session.execute(select(Video).where(Video.id.in_(video_ids))).scalars()
    }
    thumbnails = {
        t.video_id: t
        for t in session.execute(
            select(Thumbnail).where(Thumbnail.video_id.in_(video_ids))
        ).scalars()
    }

    items = []
    for pool_video in pool_videos:
        video = videos.get(pool_video.video_id)
        if video is None:
            # Defensive: pool.py's candidates come from the same videos table, so this
            # should never happen outside a race with a concurrent delete.
            continue
        items.append(
            LabelPoolItem(
                video_id=pool_video.video_id,
                title=video.title,
                channel_id=pool_video.channel_id,
                channel_handle=pool_video.channel_handle,
                published_at=pool_video.published_at,
                duration_seconds=video.duration_seconds,
                view_count=video.view_count,
                like_count=video.like_count,
                comment_count=video.comment_count,
                thumbnail_url=presigned_thumbnail_url(
                    s3_client, thumbnails.get(pool_video.video_id)
                ),
            )
        )
    return items


@labels_router.get("/pool", response_model=LabelPoolResponse)
def get_label_pool(
    mode: Literal["pool", "consistency"] = "pool",
    per_channel_max: int = Query(30, ge=1),
    pool_size: int = Query(50, ge=1, le=500),
    seed: int | None = None,
    consistency_sample_size: int = Query(20, ge=1),
    session: Session = Depends(get_db),  # noqa: B008
    s3_client=Depends(get_s3),  # noqa: B008
) -> LabelPoolResponse:
    """Wraps the same candidate_videos/sample_pool logic the CLI's `slop label run` uses
    (Phase 2), so the web labeling page preserves the same per-channel-max and
    corpus-shape guarantees - not a simplified web-only heuristic."""
    if mode == "consistency":
        pool_videos = consistency_sample(session, n=consistency_sample_size, seed=seed)
    else:
        candidates = candidate_videos(
            session, per_channel_max=per_channel_max, exclude_labeled=True
        )
        pool_videos = sample_pool(candidates, target_size=pool_size, seed=seed)

    return LabelPoolResponse(items=_pool_items_for(session, s3_client, pool_videos))


@labels_router.get("/channel-pool", response_model=ChannelBatchPoolResponse)
def get_channel_batch_pool(
    pool_size: int = Query(10, ge=1, le=200),
    seed: int | None = None,
    session: Session = Depends(get_db),  # noqa: B008
    s3_client=Depends(get_s3),  # noqa: B008
) -> ChannelBatchPoolResponse:
    """Channel-batch labeling's pool - the project's current primary labeling
    methodology (see docs/writeups/TODO.md). `pool_size` here counts CHANNELS, not
    videos - each channel in the response carries its own (already small, ~10-video)
    batch. Wraps candidate_channel_batches/sample_channel_batches, the same
    wrap-not-reimplement shape as GET /labels/pool."""
    batches = candidate_channel_batches(session, exclude_labeled=True)
    sampled = sample_channel_batches(batches, target_size=pool_size, seed=seed)

    items = [
        ChannelBatchPoolItem(
            channel_id=batch.channel_id,
            channel_handle=batch.channel_handle,
            videos=_pool_items_for(session, s3_client, batch.videos),
        )
        for batch in sampled
    ]
    return ChannelBatchPoolResponse(items=items)


def _resolve_labeler(requested: str | None) -> str:
    labeler = requested or get_settings().labeler_name
    if not labeler:
        raise HTTPException(
            status_code=400,
            detail="labeler is required (set LABELER_NAME or pass labeler explicitly)",
        )
    return labeler


@labels_router.post("", response_model=LabelResponse, status_code=201)
def create_label(
    request: LabelCreateRequest,
    session: Session = Depends(get_db),  # noqa: B008
) -> LabelResponse:
    labeler = _resolve_labeler(request.labeler)

    if session.get(Video, request.video_id) is None:
        raise HTTPException(status_code=404, detail=f"Video {request.video_id!r} not found")

    created_at = datetime.now(UTC)
    record_label(
        session,
        video_id=request.video_id,
        labeler=labeler,
        label=request.label,
        notes=request.notes,
    )

    return LabelResponse(
        video_id=request.video_id,
        labeler=labeler,
        label=request.label,
        notes=request.notes,
        created_at=created_at,
    )


@labels_router.post("/batch", response_model=BatchLabelResponse, status_code=201)
def create_batch_label(
    request: BatchLabelCreateRequest,
    session: Session = Depends(get_db),  # noqa: B008
) -> BatchLabelResponse:
    """Applies ONE label to every video in request.video_ids at once - the channel-batch
    labeling primitive (see docs/writeups/TODO.md). Still just N ordinary Label rows
    under the hood, via the same record_label call the single-video endpoint uses, so
    every downstream consumer (slop label stats, make-splits, assemble_dataset, GET
    /labels) needs zero changes - a batch label IS, structurally, several per-video
    labels created together. Atomic: get_db's session_scope() commits once at the end of
    the request, so a failure partway through rolls back the whole batch, not some of it.
    """
    labeler = _resolve_labeler(request.labeler)

    if not request.video_ids:
        raise HTTPException(status_code=400, detail="video_ids must not be empty")

    found_video_ids = set(
        session.execute(
            select(Video.id).where(
                Video.id.in_(request.video_ids), Video.channel_id == request.channel_id
            )
        ).scalars()
    )
    if found_video_ids != set(request.video_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more video_ids were not found, or do not belong to channel_id",
        )

    created_at = datetime.now(UTC)
    for video_id in request.video_ids:
        record_label(
            session, video_id=video_id, labeler=labeler, label=request.label, notes=request.notes
        )

    return BatchLabelResponse(
        channel_id=request.channel_id,
        labeler=labeler,
        label=request.label,
        video_count=len(request.video_ids),
        created_at=created_at,
    )


@labels_router.get("", response_model=LabeledVideoListResponse)
def list_labeled_videos(
    q: str | None = None,
    label: Literal["up", "down", "skip"] | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),  # noqa: B008
    s3_client=Depends(get_s3),  # noqa: B008
) -> LabeledVideoListResponse:
    """Browse/search/relabel view for the web dashboard. Shows each labeled video's MOST
    RECENT judgment (`.distinct(Label.video_id)` compiles to Postgres's DISTINCT ON,
    ordered by created_at desc - a video relabeled 3 times appears once, as its latest
    label). `slop label stats` answers a different question (aggregate counts), this
    answers "what did I label and can I find/fix a specific one".

    Secondary sort on `id` (always strictly increasing) because `created_at` uses
    `server_default=func.now()`, which returns the enclosing TRANSACTION's start time -
    two labels for the same video inserted in one transaction get an identical
    `created_at`, which would otherwise make "latest" a coin flip between them.
    """
    latest = (
        select(Label.video_id, Label.label, Label.labeler, Label.created_at)
        .distinct(Label.video_id)
        .order_by(Label.video_id, Label.created_at.desc(), Label.id.desc())
        .subquery()
    )
    counts = (
        select(Label.video_id, func.count(Label.id).label("label_count"))
        .group_by(Label.video_id)
        .subquery()
    )

    def _apply_filters(query):
        if q:
            query = query.where(Video.title.ilike(f"%{q}%"))
        if label is not None:
            query = query.where(latest.c.label == label)
        return query

    count_query = _apply_filters(
        select(func.count()).select_from(latest).join(Video, Video.id == latest.c.video_id)
    )
    total = session.execute(count_query).scalar_one()

    list_query = _apply_filters(
        select(
            latest.c.video_id,
            latest.c.label,
            latest.c.labeler,
            latest.c.created_at,
            counts.c.label_count,
            Video.title,
            Video.channel_id,
            Channel.handle,
        )
        .join(Video, Video.id == latest.c.video_id)
        .join(Channel, Channel.id == Video.channel_id)
        .join(counts, counts.c.video_id == latest.c.video_id)
    )
    rows = session.execute(
        list_query.order_by(latest.c.created_at.desc()).limit(limit).offset(offset)
    ).all()

    video_ids = [row.video_id for row in rows]
    thumbnails = {
        t.video_id: t
        for t in session.execute(
            select(Thumbnail).where(Thumbnail.video_id.in_(video_ids))
        ).scalars()
    }

    items = [
        LabeledVideoItem(
            video_id=row.video_id,
            title=row.title,
            channel_id=row.channel_id,
            channel_handle=row.handle,
            thumbnail_url=presigned_thumbnail_url(s3_client, thumbnails.get(row.video_id)),
            label=row.label,
            labeler=row.labeler,
            labeled_at=row.created_at,
            label_count=row.label_count,
        )
        for row in rows
    ]
    return LabeledVideoListResponse(items=items, total=total, limit=limit, offset=offset)
