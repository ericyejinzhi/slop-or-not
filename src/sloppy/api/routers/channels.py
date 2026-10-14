from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sloppy.api.dependencies import get_db
from sloppy.api.routers.videos import resolve_model
from sloppy.api.schemas import ChannelDetail, ChannelListItem, ChannelListResponse
from sloppy.config import get_settings
from sloppy.db.models import Channel, Video, VideoScore
from sloppy.models.scoring import SCORE_THRESHOLD

channels_router = APIRouter(prefix="/channels", tags=["channels"])


def channel_predicted_label(score: float | None) -> Literal["up", "down"] | None:
    """Same convention as a video's predicted_label: "down" (slop) at or above the
    threshold, "up" below it."""
    if score is None:
        return None
    return "down" if score >= SCORE_THRESHOLD else "up"


def _scores_by_channel(model_name: str, model_version: str):
    """Subquery: one row per channel with the mean of its videos' scores under the model
    and how many of its videos have one."""
    return (
        select(
            Video.channel_id.label("channel_id"),
            func.avg(VideoScore.score).label("score"),
            func.count(VideoScore.video_id).label("scored"),
        )
        .join(VideoScore, VideoScore.video_id == Video.id)
        .where(VideoScore.model_name == model_name, VideoScore.model_version == model_version)
        .group_by(Video.channel_id)
        .subquery()
    )


def _ingested_counts():
    return (
        select(Video.channel_id.label("channel_id"), func.count(Video.id).label("ingested"))
        .group_by(Video.channel_id)
        .subquery()
    )


@channels_router.get("", response_model=ChannelListResponse)
def list_channels(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: Literal["score", "title", "subscriber_count", "ingested_video_count"] = "score",
    order: Literal["asc", "desc"] = "desc",
    predicted_label: Literal["up", "down"] | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    session: Session = Depends(get_db),  # noqa: B008
) -> ChannelListResponse:
    """Channels with at least one ingested video, ranked by channel score (the mean of their
    videos' scores under the active model). With no model configured every score is null."""
    name, version = resolve_model(get_settings(), model_name, model_version)
    counts = _ingested_counts()
    scores = _scores_by_channel(name, version) if name is not None else None

    columns = [Channel, counts.c.ingested]
    if scores is not None:
        columns += [scores.c.score, scores.c.scored]
    stmt = select(*columns).join(counts, counts.c.channel_id == Channel.id)
    if scores is not None:
        stmt = stmt.outerjoin(scores, scores.c.channel_id == Channel.id)

    if predicted_label is not None:
        if scores is None:
            stmt = stmt.where(False)  # nothing is scored, so nothing can match
        elif predicted_label == "down":
            stmt = stmt.where(scores.c.score >= SCORE_THRESHOLD)
        else:
            stmt = stmt.where(scores.c.score < SCORE_THRESHOLD)

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    sort_columns = {
        "title": func.lower(Channel.title),
        "subscriber_count": Channel.subscriber_count,
        "ingested_video_count": counts.c.ingested,
    }
    if scores is not None:
        sort_columns["score"] = scores.c.score
    sort_column = sort_columns.get(sort, func.lower(Channel.title))
    ordered = sort_column.desc() if order == "desc" else sort_column.asc()
    # unscored channels last, whichever way it is sorted
    stmt = stmt.order_by(ordered.nulls_last(), Channel.id).limit(limit).offset(offset)

    items = []
    for row in session.execute(stmt):
        channel, ingested = row[0], row[1]
        score = float(row[2]) if scores is not None and row[2] is not None else None
        scored = int(row[3]) if scores is not None and row[3] is not None else 0
        items.append(
            ChannelListItem(
                id=channel.id,
                handle=channel.handle,
                title=channel.title,
                subscriber_count=channel.subscriber_count,
                ingested_video_count=int(ingested),
                scored_video_count=scored,
                channel_score=score,
                channel_predicted_label=channel_predicted_label(score),
            )
        )
    return ChannelListResponse(items=items, total=total, limit=limit, offset=offset)


@channels_router.get("/{channel_id}", response_model=ChannelDetail)
def get_channel_detail(
    channel_id: str,
    model_name: str | None = None,
    model_version: str | None = None,
    session: Session = Depends(get_db),  # noqa: B008
) -> ChannelDetail:
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id!r} not found")

    ingested = session.execute(
        select(func.count(Video.id)).where(Video.channel_id == channel_id)
    ).scalar_one()

    score: float | None = None
    scored = 0
    name, version = resolve_model(get_settings(), model_name, model_version)
    if name is not None:
        row = session.execute(
            select(func.avg(VideoScore.score), func.count(VideoScore.video_id))
            .join(Video, Video.id == VideoScore.video_id)
            .where(
                Video.channel_id == channel_id,
                VideoScore.model_name == name,
                VideoScore.model_version == version,
            )
        ).one()
        score = float(row[0]) if row[0] is not None else None
        scored = int(row[1])

    return ChannelDetail.model_validate(channel).model_copy(
        update={
            "channel_score": score,
            "channel_predicted_label": channel_predicted_label(score),
            "ingested_video_count": int(ingested),
            "scored_video_count": scored,
        }
    )
