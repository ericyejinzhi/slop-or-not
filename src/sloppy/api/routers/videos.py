from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sloppy.api.dependencies import get_db, get_s3
from sloppy.api.schemas import (
    NlpFeatureBreakdown,
    SimilarVideo,
    VideoDetail,
    VideoListItem,
    VideoListResponse,
    VisionFeatureBreakdown,
)
from sloppy.api.thumbnails import presigned_thumbnail_url
from sloppy.config import Settings, get_settings
from sloppy.db.models import (
    Channel,
    Thumbnail,
    Video,
    VideoNlpFeatures,
    VideoScore,
    VideoVisionFeatures,
)
from sloppy.features.similarity import nearest_videos_by_thumbnail

videos_router = APIRouter(prefix="/videos", tags=["videos"])

_SORT_COLUMNS = {
    "published_at": Video.published_at,
    "view_count": Video.view_count,
    "score": VideoScore.score,
}


def _resolve_model(
    settings: Settings, model_name: str | None, model_version: str | None
) -> tuple[str, str] | tuple[None, None]:
    """If neither an override nor Settings.active_model_name/version is set, callers
    treat this as "no model" and show null scores rather than erroring - matches "no
    trained model exists yet" being the current real state of the project."""
    name = model_name or settings.active_model_name
    version = model_version or settings.active_model_version
    if not name or not version:
        return None, None
    return name, version


@videos_router.get("", response_model=VideoListResponse)
def list_videos(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: Literal["published_at", "view_count", "score"] = "published_at",
    order: Literal["asc", "desc"] = "desc",
    channel_id: str | None = None,
    predicted_label: Literal["up", "down"] | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    session: Session = Depends(get_db),  # noqa: B008
    s3_client=Depends(get_s3),  # noqa: B008
) -> VideoListResponse:
    resolved_name, resolved_version = _resolve_model(get_settings(), model_name, model_version)
    # An unresolved model uses "" for both, which never matches a real (non-empty)
    # model_name/version - the outerjoin then simply finds nothing, giving null scores
    # uniformly instead of branching the query on whether a model is active.
    join_name = resolved_name or ""
    join_version = resolved_version or ""
    score_join_on = (
        (VideoScore.video_id == Video.id)
        & (VideoScore.model_name == join_name)
        & (VideoScore.model_version == join_version)
    )

    def _apply_filters(query):
        if channel_id is not None:
            query = query.where(Video.channel_id == channel_id)
        if predicted_label is not None:
            query = query.where(VideoScore.predicted_label == predicted_label)
        return query

    count_query = _apply_filters(
        select(func.count())
        .select_from(Video)
        .join(Channel, Channel.id == Video.channel_id)
        .outerjoin(VideoScore, score_join_on)
    )
    total = session.execute(count_query).scalar_one()

    sort_col = _SORT_COLUMNS[sort]
    order_by = sort_col.desc() if order == "desc" else sort_col.asc()

    list_query = _apply_filters(
        select(Video, Channel.handle, VideoScore.score, VideoScore.predicted_label)
        .join(Channel, Channel.id == Video.channel_id)
        .outerjoin(VideoScore, score_join_on)
    )
    rows = session.execute(list_query.order_by(order_by).limit(limit).offset(offset)).all()

    video_ids = [video.id for video, _, _, _ in rows]
    thumbnails = {
        t.video_id: t
        for t in session.execute(
            select(Thumbnail).where(Thumbnail.video_id.in_(video_ids))
        ).scalars()
    }

    items = [
        VideoListItem(
            id=video.id,
            title=video.title,
            channel_id=video.channel_id,
            channel_handle=channel_handle,
            published_at=video.published_at,
            view_count=video.view_count,
            thumbnail_url=presigned_thumbnail_url(s3_client, thumbnails.get(video.id)),
            score=score,
            predicted_label=predicted_label_value,
        )
        for video, channel_handle, score, predicted_label_value in rows
    ]
    return VideoListResponse(items=items, total=total, limit=limit, offset=offset)


@videos_router.get("/{video_id}", response_model=VideoDetail)
def get_video_detail(
    video_id: str,
    model_name: str | None = None,
    model_version: str | None = None,
    session: Session = Depends(get_db),  # noqa: B008
    s3_client=Depends(get_s3),  # noqa: B008
) -> VideoDetail:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail=f"Video {video_id!r} not found")

    channel = session.get(Channel, video.channel_id)
    resolved_name, resolved_version = _resolve_model(get_settings(), model_name, model_version)
    score_row = (
        session.get(VideoScore, (video_id, resolved_name, resolved_version))
        if resolved_name is not None
        else None
    )

    nlp = session.get(VideoNlpFeatures, video_id)
    vision = session.get(VideoVisionFeatures, video_id)
    thumbnail = session.get(Thumbnail, video_id)

    neighbors = nearest_videos_by_thumbnail(session, video_id, k=10)
    similar_videos: list[SimilarVideo] = []
    if neighbors:
        neighbor_ids = [neighbor_id for neighbor_id, _ in neighbors]
        neighbor_videos = {
            v.id: v
            for v in session.execute(select(Video).where(Video.id.in_(neighbor_ids))).scalars()
        }
        neighbor_thumbnails = {
            t.video_id: t
            for t in session.execute(
                select(Thumbnail).where(Thumbnail.video_id.in_(neighbor_ids))
            ).scalars()
        }
        for neighbor_id, distance in neighbors:
            neighbor_video = neighbor_videos.get(neighbor_id)
            if neighbor_video is None:
                # Defensive: the vision-features row outlived its video row somehow.
                continue
            similar_videos.append(
                SimilarVideo(
                    video_id=neighbor_id,
                    distance=distance,
                    title=neighbor_video.title,
                    thumbnail_url=presigned_thumbnail_url(
                        s3_client, neighbor_thumbnails.get(neighbor_id)
                    ),
                )
            )

    return VideoDetail(
        id=video.id,
        title=video.title,
        description=video.description,
        channel_id=video.channel_id,
        channel_handle=channel.handle if channel is not None else None,
        published_at=video.published_at,
        duration_seconds=video.duration_seconds,
        view_count=video.view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
        tags=video.tags or [],
        thumbnail_url=presigned_thumbnail_url(s3_client, thumbnail),
        score=score_row.score if score_row is not None else None,
        predicted_label=score_row.predicted_label if score_row is not None else None,
        model_name=resolved_name,
        model_version=resolved_version,
        nlp_features=NlpFeatureBreakdown.model_validate(nlp) if nlp is not None else None,
        vision_features=(
            VisionFeatureBreakdown.model_validate(vision) if vision is not None else None
        ),
        similar_videos=similar_videos,
    )
