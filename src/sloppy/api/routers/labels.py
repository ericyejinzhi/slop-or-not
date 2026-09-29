from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from sloppy.api.dependencies import get_db, get_s3
from sloppy.api.schemas import LabelCreateRequest, LabelPoolItem, LabelPoolResponse, LabelResponse
from sloppy.api.thumbnails import presigned_thumbnail_url
from sloppy.config import get_settings
from sloppy.db.models import Thumbnail, Video
from sloppy.label.labels import record_label
from sloppy.label.pool import candidate_videos, consistency_sample, sample_pool

labels_router = APIRouter(prefix="/labels", tags=["labels"])


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
    return LabelPoolResponse(items=items)


@labels_router.post("", response_model=LabelResponse, status_code=201)
def create_label(
    request: LabelCreateRequest,
    session: Session = Depends(get_db),  # noqa: B008
) -> LabelResponse:
    labeler = request.labeler or get_settings().labeler_name
    if not labeler:
        raise HTTPException(
            status_code=400,
            detail="labeler is required (set LABELER_NAME or pass labeler explicitly)",
        )

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
