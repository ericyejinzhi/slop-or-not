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


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
