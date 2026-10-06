"""Plain (no Prefect) ingest -> features -> score steps, shared by the API's POST /ingest
and the Prefect refresh flow (flows/refresh.py), so both do the same thing and neither
defaults to ingesting a channel's whole upload history.

A freshly ingested video has no NLP/vision features and no score; without these steps it
shows `score: null` in the dashboard forever. `refresh_channel`/`refresh_video` take a
target all the way from "never seen" to "scored with the active model".
"""

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sloppy.config import Settings
from sloppy.db.models import Video
from sloppy.db.session import session_scope
from sloppy.features.pipeline import compute_nlp_features, compute_vision_features
from sloppy.ingest.pipeline import (
    DEFAULT_SAMPLE_SIZE,
    DEFAULT_SAMPLE_WINDOW,
    IngestSummary,
    ingest_channel,
    ingest_video,
)
from sloppy.models.scoring import score_videos

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ARTIFACTS_DIR = Path("models_artifacts")

# NLP and CLIP models are large; two refreshes running at once in one process would load
# and run them concurrently for no speedup (the work is CPU-bound). Serialize them.
_refresh_lock = threading.Lock()


@dataclass
class RefreshResult:
    channel_id: str | None = None
    videos_ingested: int = 0
    nlp_processed: int = 0
    vision_processed: int = 0
    scored: int = 0
    # Why scoring didn't happen, when it didn't (e.g. no active model configured) - a
    # refresh that ingests but can't score is a normal outcome, not an error.
    score_skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)


def ingest_channel_sampled(
    settings: Settings, id_or_handle: str, max_videos: int | None = None
) -> IngestSummary:
    """Ingest a channel capped to a sensible number of videos: the `max_videos` most
    recent if given, otherwise the project's default random sample (see
    DEFAULT_SAMPLE_SIZE/WINDOW in ingest/pipeline.py)."""
    if max_videos is not None:
        return ingest_channel(settings, id_or_handle, limit=max_videos)
    return ingest_channel(
        settings,
        id_or_handle,
        sample_window=DEFAULT_SAMPLE_WINDOW,
        sample_size=DEFAULT_SAMPLE_SIZE,
    )


def score_with_active_model(
    settings: Settings, video_ids: list[str]
) -> tuple[list[str], str | None]:
    """Score `video_ids` with the configured active model. Returns (scored ids, reason it
    was skipped or None). Existing train/val/test splits are never overwritten (see
    upsert_video_score's preserve_split)."""
    if not settings.active_model_name or not settings.active_model_version:
        return [], "no active model configured (ACTIVE_MODEL_NAME/VERSION unset)"
    if not video_ids:
        return [], "no videos to score"

    scored = score_videos(
        video_ids=video_ids,
        model_name=settings.active_model_name,
        model_version=settings.active_model_version,
        artifacts_dir=DEFAULT_MODEL_ARTIFACTS_DIR,
    )
    return scored, None


def channel_video_ids(channel_id: str) -> list[str]:
    with session_scope() as session:
        rows = session.query(Video.id).filter(Video.channel_id == channel_id).all()
    return [row[0] for row in rows]


def refresh_channel(
    settings: Settings, id_or_handle: str, max_videos: int | None = None
) -> RefreshResult:
    """Ingest (capped) -> NLP features -> vision features -> score, for one channel."""
    with _refresh_lock:
        summary = ingest_channel_sampled(settings, id_or_handle, max_videos)
        if summary.channel_id is None:
            raise ValueError(f"ingest_channel did not resolve a channel id for {id_or_handle!r}")
        channel_id = summary.channel_id

        nlp = compute_nlp_features(channel_id=channel_id, only_missing=True)
        vision = compute_vision_features(settings, channel_id=channel_id, only_missing=True)
        scored, skipped = score_with_active_model(settings, channel_video_ids(channel_id))

    return RefreshResult(
        channel_id=channel_id,
        videos_ingested=summary.videos_upserted,
        nlp_processed=len(nlp),
        vision_processed=len(vision),
        scored=len(scored),
        score_skipped_reason=skipped,
        errors=summary.errors,
    )


def refresh_video(settings: Settings, video_id: str) -> RefreshResult:
    """Ingest -> NLP features -> vision features -> score, for a single video."""
    with _refresh_lock:
        summary = ingest_video(settings, video_id)
        # A video whose ingest failed was never written; computing features for it would
        # just find nothing, and scoring would skip it - report the failure instead.
        if summary.videos_upserted == 0:
            return RefreshResult(channel_id=summary.channel_id, errors=summary.errors)

        nlp = compute_nlp_features(video_id=video_id, only_missing=True)
        vision = compute_vision_features(settings, video_id=video_id, only_missing=True)
        scored, skipped = score_with_active_model(settings, [video_id])

    return RefreshResult(
        channel_id=summary.channel_id,
        videos_ingested=summary.videos_upserted,
        nlp_processed=len(nlp),
        vision_processed=len(vision),
        scored=len(scored),
        score_skipped_reason=skipped,
        errors=summary.errors,
    )
