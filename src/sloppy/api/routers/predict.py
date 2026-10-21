"""POST /predict: score one video from its YouTube link.

Unlike POST /ingest this changes nothing: no rows, no files, no labels. That is why it is
the one POST a read-only deployment still allows (see app.py). It is open to anyone who can
reach the site, so it is rate limited per client and runs one at a time - each call spends
YouTube API quota and about a minute of CPU on large models.
"""

import threading

from fastapi import APIRouter, HTTPException, Request

from sloppy.api.schemas import PredictRequest, PredictResponse
from sloppy.config import Settings
from sloppy.predict.service import predict_video

predict_router = APIRouter(prefix="/predict", tags=["predict"])

# How long a request waits for the prediction already running before giving up.
BUSY_WAIT_SECONDS = 90


def client_key(request: Request, settings: Settings) -> str:
    """Who is asking, for rate limiting. Only believes X-Real-IP when told the API sits
    behind a proxy that sets it (settings.trust_proxy_headers)."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-real-ip")
        if forwarded:
            return forwarded.strip()
    return request.client.host if request.client else "unknown"


@predict_router.post("", response_model=PredictResponse)
def create_prediction(body: PredictRequest, request: Request) -> PredictResponse:
    settings: Settings = request.app.state.settings
    limiter = request.app.state.predict_limiter
    lock: threading.Lock = request.app.state.predict_lock

    key = client_key(request, settings)
    if not limiter.allow(key):
        wait = limiter.retry_after_seconds(key)
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many predictions from your address. "
                f"Try again in about {wait // 60 + 1} minute(s)."
            ),
            headers={"Retry-After": str(wait)},
        )

    if not lock.acquire(timeout=BUSY_WAIT_SECONDS):
        raise HTTPException(
            status_code=503, detail="Another prediction is still running. Try again in a moment."
        )
    try:
        result = predict_video(settings, body.url)
    finally:
        lock.release()
    return PredictResponse(**result.to_dict())
