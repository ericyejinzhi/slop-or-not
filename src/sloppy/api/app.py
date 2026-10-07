"""FastAPI app factory. Run with: uv run uvicorn sloppy.api.app:app --reload --port 8000"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sloppy.api.errors import register_error_handlers
from sloppy.api.routers.channels import channels_router
from sloppy.api.routers.ingest import ingest_router
from sloppy.api.routers.labels import labels_router
from sloppy.api.routers.videos import videos_router
from sloppy.config import Settings, get_settings

# Methods that cannot change state. Everything else is rejected in read-only mode, so a
# write endpoint added later is blocked by default rather than needing to be remembered.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title="slop-or-not", version="0.1.0")

    if settings.read_only:

        @app.middleware("http")
        async def reject_writes(request: Request, call_next):
            if request.method not in SAFE_METHODS:
                return JSONResponse(
                    status_code=403, content={"detail": "This deployment is read-only"}
                )
            return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    def app_config() -> dict[str, bool]:
        """What the frontend needs to know to adapt: hide controls that cannot work."""
        return {"read_only": settings.read_only}

    app.include_router(videos_router)
    app.include_router(channels_router)
    app.include_router(ingest_router)
    app.include_router(labels_router)
    register_error_handlers(app)

    return app


app = create_app()
