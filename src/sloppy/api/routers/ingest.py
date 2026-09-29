"""POST /ingest schedules ingestion via FastAPI's BackgroundTasks (fire-and-forget, no
job-status tracking) - a deliberate placeholder; real orchestration (retries,
scheduling, persisted job state) is Phase 7's job (Prefect), not this one's.
"""

from fastapi import APIRouter, BackgroundTasks

from sloppy.api.schemas import IngestRequest, IngestResponse
from sloppy.config import get_settings
from sloppy.ingest.pipeline import ingest_channel, ingest_video

ingest_router = APIRouter(prefix="/ingest", tags=["ingest"])


@ingest_router.post("", response_model=IngestResponse, status_code=202)
def create_ingest(request: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    settings = get_settings()
    if request.channel is not None:
        background_tasks.add_task(ingest_channel, settings, request.channel)
        return IngestResponse(status="accepted", target=request.channel)

    background_tasks.add_task(ingest_video, settings, request.video_id)
    return IngestResponse(status="accepted", target=request.video_id)
