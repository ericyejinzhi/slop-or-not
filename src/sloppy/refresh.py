"""Plain (no Prefect) ingest -> features -> score steps, shared by the API's POST /ingest
and the Prefect refresh flow (flows/refresh.py), so both do the same thing and neither
defaults to ingesting a channel's whole upload history.

A freshly ingested video has no NLP/vision features and no score; without these steps it
shows `score: null` in the dashboard forever. `refresh_channel`/`refresh_video` take a
target all the way from "never seen" to "scored with the active model".
"""

import json
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
from sloppy.models.artifact_store import ensure_local_model
from sloppy.models.scoring import score_videos
from sloppy.models.train import (
    TEXT_CATEGORICAL_FEATURES,
    TEXT_NUMERIC_FEATURES,
    VISION_CATEGORICAL_FEATURES,
    VISION_NUMERIC_FEATURES,
)

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
    # Feature steps not run because the active model doesn't use them ("nlp", "vision").
    features_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def active_model_feature_needs(settings: Settings) -> tuple[bool, bool]:
    """(needs_text, needs_vision): whether the active model uses any NLP-derived or any
    CLIP-derived feature, read from the `features` list in its saved metadata.json. A model
    trained on the 'metadata' feature group needs neither, so refreshing a channel can skip
    the slow NLP/CLIP computation (and not load those models into the process at all).
    Anything unknown - no active model, a missing or unreadable artifact - returns
    (True, True): compute everything, the safe previous behavior."""
    if not settings.active_model_name or not settings.active_model_version:
        return True, True
    ensure_local_model(
        settings,
        DEFAULT_MODEL_ARTIFACTS_DIR,
        settings.active_model_name,
        settings.active_model_version,
    )
    path = (
        DEFAULT_MODEL_ARTIFACTS_DIR
        / settings.active_model_name
        / settings.active_model_version
        / "metadata.json"
    )
    try:
        features = set(json.loads(path.read_text(encoding="utf-8"))["features"])
    except (OSError, ValueError, KeyError):
        logger.warning("Cannot read the active model's feature list at %s; computing all", path)
        return True, True

    text = features & set(TEXT_NUMERIC_FEATURES + TEXT_CATEGORICAL_FEATURES)
    vision = features & set(VISION_NUMERIC_FEATURES + VISION_CATEGORICAL_FEATURES)
    return bool(text), bool(vision)


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

    ensure_local_model(
        settings,
        DEFAULT_MODEL_ARTIFACTS_DIR,
        settings.active_model_name,
        settings.active_model_version,
    )
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
    """Ingest (capped) -> NLP features -> vision features -> score, for one channel. The
    NLP/vision steps are skipped when the active model doesn't use them."""
    needs_text, needs_vision = active_model_feature_needs(settings)
    with _refresh_lock:
        summary = ingest_channel_sampled(settings, id_or_handle, max_videos)
        if summary.channel_id is None:
            raise ValueError(f"ingest_channel did not resolve a channel id for {id_or_handle!r}")
        channel_id = summary.channel_id

        nlp = compute_nlp_features(channel_id=channel_id, only_missing=True) if needs_text else []
        vision = (
            compute_vision_features(settings, channel_id=channel_id, only_missing=True)
            if needs_vision
            else []
        )
        scored, skipped = score_with_active_model(settings, channel_video_ids(channel_id))

    return RefreshResult(
        channel_id=channel_id,
        videos_ingested=summary.videos_upserted,
        nlp_processed=len(nlp),
        vision_processed=len(vision),
        scored=len(scored),
        score_skipped_reason=skipped,
        features_skipped=_skipped_steps(needs_text, needs_vision),
        errors=summary.errors,
    )


def _skipped_steps(needs_text: bool, needs_vision: bool) -> list[str]:
    return [name for name, needed in (("nlp", needs_text), ("vision", needs_vision)) if not needed]


def refresh_video(settings: Settings, video_id: str) -> RefreshResult:
    """Ingest -> NLP features -> vision features -> score, for a single video. The
    NLP/vision steps are skipped when the active model doesn't use them."""
    needs_text, needs_vision = active_model_feature_needs(settings)
    with _refresh_lock:
        summary = ingest_video(settings, video_id)
        # A video whose ingest failed was never written; computing features for it would
        # just find nothing, and scoring would skip it - report the failure instead.
        if summary.videos_upserted == 0:
            return RefreshResult(channel_id=summary.channel_id, errors=summary.errors)

        nlp = compute_nlp_features(video_id=video_id, only_missing=True) if needs_text else []
        vision = (
            compute_vision_features(settings, video_id=video_id, only_missing=True)
            if needs_vision
            else []
        )
        scored, skipped = score_with_active_model(settings, [video_id])

    return RefreshResult(
        channel_id=summary.channel_id,
        videos_ingested=summary.videos_upserted,
        nlp_processed=len(nlp),
        vision_processed=len(vision),
        scored=len(scored),
        score_skipped_reason=skipped,
        features_skipped=_skipped_steps(needs_text, needs_vision),
        errors=summary.errors,
    )
