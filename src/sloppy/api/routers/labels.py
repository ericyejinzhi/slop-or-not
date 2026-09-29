from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from sloppy.api.dependencies import get_db
from sloppy.api.schemas import LabelCreateRequest, LabelResponse
from sloppy.config import get_settings
from sloppy.db.models import Video
from sloppy.label.labels import record_label

labels_router = APIRouter(prefix="/labels", tags=["labels"])


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
