"""FastAPI app factory. Run with: uv run uvicorn sloppy.api.app:app --reload --port 8000"""

from fastapi import FastAPI

from sloppy.api.errors import register_error_handlers
from sloppy.api.routers.channels import channels_router
from sloppy.api.routers.ingest import ingest_router
from sloppy.api.routers.labels import labels_router
from sloppy.api.routers.videos import videos_router


def create_app() -> FastAPI:
    app = FastAPI(title="slop-or-not", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(videos_router)
    app.include_router(channels_router)
    app.include_router(ingest_router)
    app.include_router(labels_router)
    register_error_handlers(app)

    return app


app = create_app()
