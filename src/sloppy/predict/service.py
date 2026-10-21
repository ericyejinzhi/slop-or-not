"""Predict whether one YouTube video is slop, from its link.

Everything is computed in memory from what YouTube returns for that one video. The only
database access is READ-ONLY (corpus norms for the genre, thumbnail neighbours, whether the
channel is already known); nothing is inserted, updated or uploaded, so a prediction never
changes the dataset. Adding a video to the dataset stays an admin action (POST /ingest).

The model used is the configured video-only model: one trained without the features that
compare a video with the rest of its channel, because a pasted link gives us no channel
history to compute them from.
"""

import io
import json
import logging
import urllib.error
from dataclasses import asdict, dataclass, field
from pathlib import Path

import joblib
import pandas as pd
from googleapiclient.errors import HttpError
from PIL import Image
from sqlalchemy import func, select

from sloppy.config import Settings
from sloppy.db.models import Video, VideoScore
from sloppy.db.session import session_scope
from sloppy.features.corpus import build_corpus_stats
from sloppy.features.extract import extract_features
from sloppy.features.interactions import lure_score_x_genre, mysterious_score_x_duration_bucket
from sloppy.features.pipeline import nlp_feature_values
from sloppy.features.similarity import (
    near_duplicate_count_for_embedding,
    nearest_videos_for_embedding,
)
from sloppy.features.vision import embed_image, zero_shot_scores
from sloppy.ingest.pipeline import COMMENTS_PER_VIDEO
from sloppy.ingest.thumbnails import download_thumbnail_bytes, extract_thumbnail_url
from sloppy.ingest.youtube import (
    VideoMeta,
    fetch_top_comments,
    fetch_videos_metadata,
    get_youtube_client,
    resolve_channel,
)
from sloppy.models.artifact_store import ensure_local_model
from sloppy.models.train import CHANNEL_CONTEXT_FEATURES
from sloppy.predict.errors import PredictionUnavailable, VideoNotFound
from sloppy.predict.explain import explain_prediction
from sloppy.predict.url import parse_video_id

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ARTIFACTS_DIR = Path("models_artifacts")
SCORE_THRESHOLD = 0.5
TOP_FACTORS = 6
SIMILAR_VIDEOS = 5


@dataclass
class Factor:
    feature: str
    label: str
    value: float | str | None
    contribution: float  # log-odds; positive pushes toward slop


@dataclass
class SimilarVideo:
    video_id: str
    title: str
    distance: float
    score: float | None


@dataclass
class ChannelContext:
    channel_id: str
    title: str | None
    in_dataset: bool
    # Mean of this channel's stored video scores under the same model. None when there is
    # nothing to average (channel not in the dataset, or not yet scored by this model).
    channel_score: float | None = None
    scored_video_count: int = 0


@dataclass
class PredictionResult:
    video_id: str
    title: str
    thumbnail_url: str | None
    score: float
    predicted_label: str  # "down" = slop, "up" = not slop
    factors: list[Factor]
    similar_videos: list[SimilarVideo]
    channel: ChannelContext
    model_name: str
    model_version: str
    comments_used: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _load_model(settings: Settings, artifacts_dir: Path):
    name, version = settings.video_only_model_name, settings.video_only_model_version
    if not name or not version:
        raise PredictionUnavailable("Predictions are not set up on this server.")
    try:
        ensure_local_model(settings, artifacts_dir, name, version)
        model_dir = artifacts_dir / name / version
        pipeline = joblib.load(model_dir / "model.joblib")
        metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        logger.exception("Could not load the video-only model")
        raise PredictionUnavailable("The prediction model could not be loaded.") from exc

    if set(metadata["features"]) & set(CHANNEL_CONTEXT_FEATURES):
        raise PredictionUnavailable(
            "The configured model needs channel history, which a single link does not "
            "provide. Train one with --feature-group video_only."
        )
    return pipeline, metadata


def _fetch_from_youtube(settings: Settings, video_id: str):
    """(meta, comment texts, channel title, warnings). YouTube failures on the video itself
    abort; failures on the extras (comments, channel title) degrade with a warning."""
    if not settings.youtube_api_key:
        raise PredictionUnavailable("Predictions are not set up on this server.")
    warnings: list[str] = []
    client = get_youtube_client(settings)

    try:
        found = fetch_videos_metadata(client, [video_id])
    except HttpError as exc:
        logger.exception("YouTube lookup failed")
        raise PredictionUnavailable(
            "YouTube could not be reached right now (the daily quota may be used up). "
            "Try again later."
        ) from exc
    if not found:
        raise VideoNotFound("YouTube has no public video with that link.")
    meta = found[0]

    try:
        comments = [c.text for c in fetch_top_comments(client, video_id, COMMENTS_PER_VIDEO)]
    except HttpError:
        logger.exception("Could not fetch comments for %s", video_id)
        comments = []
        warnings.append("Comments could not be fetched, so comment signals were left out.")
    if not comments and not warnings:
        warnings.append("This video has no comments, so comment signals were left out.")

    try:
        channel_title = resolve_channel(client, meta.channel_id).title
    except (HttpError, ValueError):
        channel_title = None

    return meta, comments, channel_title, warnings


def _load_thumbnail(video_id: str, meta: VideoMeta) -> Image.Image | None:
    """Same source as ingestion (yt-dlp's best thumbnail), falling back to the API's URL."""
    urls: list[str] = []
    try:
        urls.append(extract_thumbnail_url(video_id).url)
    except Exception:  # noqa: BLE001 - yt-dlp raises many types; any failure means fall back
        logger.warning("yt-dlp thumbnail lookup failed for %s", video_id)
    if meta.thumbnail_url:
        urls.append(meta.thumbnail_url)

    for url in urls:
        try:
            content, _ = download_thumbnail_bytes(url)
            return Image.open(io.BytesIO(content)).convert("RGB")
        except (urllib.error.URLError, OSError, ValueError):
            logger.warning("Could not download or open thumbnail %s", url)
    return None


def _record(
    meta: VideoMeta, comments: list[str], image: Image.Image | None, session, warnings
) -> tuple[dict, list[float] | None]:
    """One row of video-level features, built exactly as the training pipeline builds them
    (the same functions), from in-memory inputs. Returns (row, thumbnail embedding)."""
    stored = list(session.execute(select(Video)).scalars())
    # The duration norms are built from the stored corpus, and count this video itself the
    # way training does (a stored video is already in it).
    corpus_videos = stored if any(v.id == meta.id for v in stored) else [*stored, meta]
    record = asdict(extract_features(meta, build_corpus_stats(corpus_videos)))

    nlp = asdict(nlp_feature_values(meta.title, meta.description, comments))
    for column in (
        "sentiment_mean",
        "sentiment_std",
        "sentiment_negative_share",
        "slop_keyword_rate",
        "topic_cluster_count",
        "topic_top_cluster_share",
        "topic_top_cluster_sentiment",
        "topic_sentiment_spread",
        "title_lure_score",
        "title_mysterious_score",
        "title_transparent_score",
    ):
        record[column] = nlp[column]

    embedding: list[float] | None = None
    if image is not None:
        try:
            embedding = embed_image(image).tolist()
            record.update(zero_shot_scores(image))
            record["near_duplicate_thumbnail_count"] = near_duplicate_count_for_embedding(
                session, embedding
            )
        except Exception:  # noqa: BLE001 - a bad image must not sink the whole prediction
            logger.exception("Thumbnail features failed for %s", meta.id)
            embedding = None
            warnings.append(
                "The thumbnail could not be analysed, so thumbnail signals were left out."
            )
    else:
        warnings.append("The thumbnail could not be fetched, so thumbnail signals were left out.")

    record["lure_score_x_genre"] = lure_score_x_genre(record["title_lure_score"], record["genre"])
    record["mysterious_score_x_duration_bucket"] = mysterious_score_x_duration_bucket(
        record["title_mysterious_score"], record["duration_bucket"]
    )
    return record, embedding


def _context(
    session, settings: Settings, meta: VideoMeta, channel_title: str | None, embedding
) -> tuple[ChannelContext, list[SimilarVideo]]:
    name, version = settings.video_only_model_name, settings.video_only_model_version

    average, scored_count = session.execute(
        select(func.avg(VideoScore.score), func.count(VideoScore.video_id))
        .join(Video, Video.id == VideoScore.video_id)
        .where(
            Video.channel_id == meta.channel_id,
            VideoScore.model_name == name,
            VideoScore.model_version == version,
        )
    ).one()
    stored_videos = session.execute(
        select(func.count()).select_from(Video).where(Video.channel_id == meta.channel_id)
    ).scalar_one()
    channel = ChannelContext(
        channel_id=meta.channel_id,
        title=channel_title,
        in_dataset=stored_videos > 0,
        channel_score=float(average) if average is not None else None,
        scored_video_count=int(scored_count),
    )

    similar: list[SimilarVideo] = []
    if embedding is not None:
        neighbours = nearest_videos_for_embedding(
            session, embedding, k=SIMILAR_VIDEOS, exclude_video_id=meta.id
        )
        titles = dict(
            session.execute(
                select(Video.id, Video.title).where(Video.id.in_([v for v, _ in neighbours]))
            ).all()
        )
        scores = dict(
            session.execute(
                select(VideoScore.video_id, VideoScore.score).where(
                    VideoScore.video_id.in_([v for v, _ in neighbours]),
                    VideoScore.model_name == name,
                    VideoScore.model_version == version,
                )
            ).all()
        )
        similar = [
            SimilarVideo(v, titles.get(v, ""), distance, scores.get(v))
            for v, distance in neighbours
        ]
    return channel, similar


def predict_video(
    settings: Settings, link: str, artifacts_dir: Path = DEFAULT_MODEL_ARTIFACTS_DIR
) -> PredictionResult:
    """Score one video from its link. Raises InvalidVideoLink, VideoNotFound or
    PredictionUnavailable; see predict/errors.py. Writes nothing."""
    video_id = parse_video_id(link)
    pipeline, metadata = _load_model(settings, artifacts_dir)
    numeric, categorical = metadata["numeric_features"], metadata["categorical_features"]

    meta, comments, channel_title, warnings = _fetch_from_youtube(settings, video_id)
    image = _load_thumbnail(video_id, meta)

    with session_scope() as session:
        record, embedding = _record(meta, comments, image, session, warnings)

        row = pd.DataFrame([record]).reindex(columns=numeric + categorical)
        # A one-row frame holds None, not NaN, in numeric columns; coerce so the imputer sees
        # them as missing values.
        for column in numeric:
            row[column] = pd.to_numeric(row[column], errors="coerce")

        probabilities = pipeline.predict_proba(row)
        score = float(probabilities[0][list(pipeline.classes_).index(1)])
        factors = explain_prediction(pipeline, row, numeric, categorical)[:TOP_FACTORS]
        channel, similar = _context(session, settings, meta, channel_title, embedding)

    return PredictionResult(
        video_id=video_id,
        title=meta.title,
        thumbnail_url=meta.thumbnail_url,
        score=score,
        predicted_label="down" if score >= SCORE_THRESHOLD else "up",
        factors=[Factor(f.feature, f.label, f.value, f.contribution) for f in factors],
        similar_videos=similar,
        channel=channel,
        model_name=settings.video_only_model_name,
        model_version=settings.video_only_model_version,
        comments_used=len(comments),
        warnings=warnings,
    )
