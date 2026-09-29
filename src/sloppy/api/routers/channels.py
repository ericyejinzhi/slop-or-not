from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from sloppy.api.dependencies import get_db
from sloppy.api.schemas import ChannelDetail
from sloppy.db.models import Channel

channels_router = APIRouter(prefix="/channels", tags=["channels"])


@channels_router.get("/{channel_id}", response_model=ChannelDetail)
def get_channel_detail(
    channel_id: str,
    session: Session = Depends(get_db),  # noqa: B008
) -> ChannelDetail:
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id!r} not found")
    return ChannelDetail.model_validate(channel)
