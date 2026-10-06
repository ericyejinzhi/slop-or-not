"""POST /ingest schedules a full refresh via FastAPI's BackgroundTasks (fire-and-forget,
no job-status tracking): ingest the target (a channel is capped to a sample, never its
whole history), compute NLP + vision features, then score with the active model - so a
video ingested from the dashboard actually ends up with a score instead of `null`.
Retries, scheduling and persisted job state are Phase 7's (Prefect) job, not this one's.
"""

import logging

from fastapi import APIRouter, BackgroundTasks

from sloppy.api.schemas import IngestRequest, IngestResponse
from sloppy.config import Settings, get_settings
from sloppy.refresh import refresh_channel, refresh_video

logger = logging.getLogger(__name__)

ingest_router = APIRouter(prefix="/ingest", tags=["ingest"])


def _run_channel_refresh(settings: Settings, channel: str, max_videos: int | None) -> None:
    # A background task has no caller to raise to; log failures with a traceback so they
    # show up in the API log instead of vanishing.
    try:
        result = refresh_channel(settings, channel, max_videos)
    except Exception:
        logger.exception("Background refresh failed for channel %r", channel)
        return
    logger.info("Refreshed channel %r: %s", channel, result)


def _run_video_refresh(settings: Settings, video_id: str) -> None:
    try:
        result = refresh_video(settings, video_id)
    except Exception:
        logger.exception("Background refresh failed for video %r", video_id)
        return
    logger.info("Refreshed video %r: %s", video_id, result)


@ingest_router.post("", response_model=IngestResponse, status_code=202)
def create_ingest(request: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    settings = get_settings()
    if request.channel is not None:
        background_tasks.add_task(
            _run_channel_refresh, settings, request.channel, request.max_videos
        )
        return IngestResponse(status="accepted", target=request.channel)

    background_tasks.add_task(_run_video_refresh, settings, request.video_id)
    return IngestResponse(status="accepted", target=request.video_id)
