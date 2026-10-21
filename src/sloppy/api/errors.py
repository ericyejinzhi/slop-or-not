"""Centralized exception handlers, registered on the app in create_app().

Every ValueError raised anywhere in this app today (resolve_channel, ingest_video) is a
"not found" case, so the blanket ValueError -> 404 mapping below is safe. If a future
ValueError is ever raised for a different reason, this mapping would need to become more
specific (e.g. a dedicated exception class) - a known simplification, not a bug.

FastAPI's own RequestValidationError (malformed query params/body against the Pydantic
schemas) already returns 422 with a useful body automatically - no custom handler needed.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from sloppy.predict.errors import InvalidVideoLink, PredictionUnavailable, VideoNotFound


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Defense in depth, not the primary validation path: the labels router already does
    # an explicit FK pre-check, and Pydantic's Literal on LabelCreateRequest.label already
    # makes the CHECK-constraint case unreachable through the API as designed. This is a
    # generic fallback for anything that reaches this far regardless.
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflicting or invalid data", "error": str(exc.orig)},
    )


async def invalid_video_link_handler(request: Request, exc: InvalidVideoLink) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def video_not_found_handler(request: Request, exc: VideoNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def prediction_unavailable_handler(
    request: Request, exc: PredictionUnavailable
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(InvalidVideoLink, invalid_video_link_handler)
    app.add_exception_handler(VideoNotFound, video_not_found_handler)
    app.add_exception_handler(PredictionUnavailable, prediction_unavailable_handler)
