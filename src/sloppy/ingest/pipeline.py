"""Phase 1 orchestration: resolve a channel, ingest its videos/comments/thumbnails, upsert.

One video's failure (deleted, comments disabled and something else also going wrong,
extraction failure, ...) is logged and skipped rather than aborting the whole run.
"""

import itertools
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sloppy.config import Settings
from sloppy.db.models import Channel
from sloppy.db.session import session_scope
from sloppy.ingest.thumbnails import (
    download_thumbnail_bytes,
    extract_thumbnail_url,
    upload_thumbnail,
)
from sloppy.ingest.upsert import upsert_channel, upsert_comment, upsert_thumbnail, upsert_video
from sloppy.ingest.youtube import (
    VideoMeta,
    fetch_top_comments,
    fetch_videos_metadata,
    get_youtube_client,
    iter_playlist_video_ids,
    resolve_channel,
)
from sloppy.storage import ensure_bucket, get_s3_client

logger = logging.getLogger(__name__)

COMMENTS_PER_VIDEO = 100
VIDEO_BATCH_SIZE = 50

# The project's default channel sample (channel-batch labeling methodology): a random
# DEFAULT_SAMPLE_SIZE of a channel's DEFAULT_SAMPLE_WINDOW most-recent uploads. The CLI,
# the API's POST /ingest and the refresh flow all share it, so no entry point defaults to
# ingesting a channel's entire (potentially thousands-of-videos) history.
DEFAULT_SAMPLE_WINDOW = 75
DEFAULT_SAMPLE_SIZE = 10


@dataclass
class IngestSummary:
    channel_id: str | None = None
    videos_upserted: int = 0
    comments_upserted: int = 0
    thumbnails_upserted: int = 0
    errors: list[str] = field(default_factory=list)


def _ingest_video(
    settings: Settings, youtube, s3_client, video: VideoMeta
) -> tuple[int, bool, Exception | None]:
    """Fetch a video's comments + thumbnail (network) and upsert in one DB transaction.

    A thumbnail failure (extraction/download/upload) does NOT discard the video's metadata
    and comments — those are still upserted, and only the thumbnail row is skipped, since
    those are independently useful data.

    Returns (comment_count, thumbnail_upserted, thumbnail_error).
    """
    comments = fetch_top_comments(youtube, video.id, limit=COMMENTS_PER_VIDEO)

    thumbnail_error: Exception | None = None
    thumbnail_kwargs: dict | None = None
    try:
        thumb_info = extract_thumbnail_url(video.id)
        content, content_type = download_thumbnail_bytes(thumb_info.url)
        key = upload_thumbnail(s3_client, settings, video.id, content, content_type)
        thumbnail_kwargs = {
            "video_id": video.id,
            "s3_bucket": settings.s3_bucket_thumbnails,
            "s3_key": key,
            "content_type": content_type,
            "width": thumb_info.width,
            "height": thumb_info.height,
            "source_url": thumb_info.url,
            "downloaded_at": datetime.now(UTC),
        }
    except Exception as exc:  # noqa: BLE001 - handled per-video, see docstring
        thumbnail_error = exc

    with session_scope() as session:
        upsert_video(session, video)
        for comment in comments:
            upsert_comment(session, comment)
        if thumbnail_kwargs is not None:
            upsert_thumbnail(session, **thumbnail_kwargs)

    return len(comments), thumbnail_kwargs is not None, thumbnail_error


def ingest_video(settings: Settings, video_id: str) -> IngestSummary:
    """Ingest a single video by id, for callers that don't want a whole-channel ingest
    (e.g. the API's POST /ingest). If the video's channel isn't in the DB yet, resolves
    and upserts it first, since `_ingest_video` never creates a Channel row and the FK
    would otherwise fail for a video from a never-seen channel.
    """
    summary = IngestSummary()
    youtube = get_youtube_client(settings)
    s3_client = get_s3_client(settings)
    ensure_bucket(s3_client, settings.s3_bucket_thumbnails)

    videos = fetch_videos_metadata(youtube, [video_id])
    if not videos:
        raise ValueError(f"No YouTube video found for {video_id!r}")
    video = videos[0]
    summary.channel_id = video.channel_id

    with session_scope() as session:
        channel_exists = session.get(Channel, video.channel_id) is not None
    if not channel_exists:
        channel = resolve_channel(youtube, video.channel_id)
        with session_scope() as session:
            upsert_channel(session, channel)

    try:
        comment_count, thumbnail_upserted, thumbnail_error = _ingest_video(
            settings, youtube, s3_client, video
        )
    except Exception as exc:  # noqa: BLE001 - a single video's failure must not raise past here
        logger.warning("Failed to ingest video %s: %s", video.id, exc)
        summary.errors.append(f"{video.id}: {exc}")
        return summary

    summary.videos_upserted += 1
    summary.comments_upserted += comment_count
    summary.thumbnails_upserted += int(thumbnail_upserted)
    if thumbnail_error is not None:
        summary.errors.append(f"{video.id}: thumbnail failed: {thumbnail_error}")

    return summary


def _sample_recent_video_ids(
    youtube, playlist_id: str, *, window: int, sample_size: int, seed: int | None = None
) -> list[str]:
    """Random sample of `sample_size` ids drawn from the `window` MOST RECENT videos
    (not the channel's entire history - channels drift/pivot, so an old video is a poor
    representative of what the channel looks like today). `window` is bounded via
    itertools.islice, same laziness property as `limit` below - a channel with thousands
    of videos still only pays for ceil(window / 50) playlistItems.list pages, never the
    whole history. Returns fewer than `sample_size` only if the channel has fewer than
    `window` videos total.
    """
    recent_ids = list(itertools.islice(iter_playlist_video_ids(youtube, playlist_id), window))
    return random.Random(seed).sample(recent_ids, min(sample_size, len(recent_ids)))


def ingest_channel(
    settings: Settings,
    id_or_handle: str,
    limit: int | None = None,
    sample_window: int | None = None,
    sample_size: int | None = None,
    sample_seed: int | None = None,
) -> IngestSummary:
    """Two mutually exclusive selection strategies for which videos to ingest:

    - `limit`: caps ingestion to the `limit` MOST RECENT videos (the uploads playlist is
      confirmed to return most-recent-first - verified directly against the real API,
      not assumed). Uses itertools.islice, not a full-list-then-truncate, so a channel
      with thousands of videos only pays for as many playlistItems.list pages as the
      limit actually needs, not the whole history.
    - `sample_window` + `sample_size` (both required together): a random sample of
      `sample_size` videos drawn from the `sample_window` most recent, via
      `_sample_recent_video_ids` above. This is the project's current primary labeling
      methodology (channel-batch labeling, see docs/writeups/TODO.md) - a small random
      sample is more representative of "what does this channel's content generally look
      like" than always taking the same most-recent N, and incidentally picks up Shorts
      without any special-casing, since they already appear in the uploads playlist.

    Passing only one of `sample_window`/`sample_size` is almost certainly a mistake
    (ambiguous what the other should default to), so it's rejected outright rather than
    silently guessing.
    """
    if (sample_window is None) != (sample_size is None):
        raise ValueError("sample_window and sample_size must be given together")

    summary = IngestSummary()
    youtube = get_youtube_client(settings)
    s3_client = get_s3_client(settings)
    ensure_bucket(s3_client, settings.s3_bucket_thumbnails)

    channel = resolve_channel(youtube, id_or_handle)
    summary.channel_id = channel.id
    with session_scope() as session:
        upsert_channel(session, channel)

    if sample_window is not None and sample_size is not None:
        video_ids = _sample_recent_video_ids(
            youtube,
            channel.uploads_playlist_id,
            window=sample_window,
            sample_size=sample_size,
            seed=sample_seed,
        )
    else:
        video_id_iter = iter_playlist_video_ids(youtube, channel.uploads_playlist_id)
        if limit is not None:
            video_id_iter = itertools.islice(video_id_iter, limit)
        video_ids = list(video_id_iter)

    for i in range(0, len(video_ids), VIDEO_BATCH_SIZE):
        batch_ids = video_ids[i : i + VIDEO_BATCH_SIZE]
        for video in fetch_videos_metadata(youtube, batch_ids):
            try:
                comment_count, thumbnail_upserted, thumbnail_error = _ingest_video(
                    settings, youtube, s3_client, video
                )
            except Exception as exc:  # noqa: BLE001 - one bad video must not abort the run
                logger.warning("Failed to ingest video %s: %s", video.id, exc)
                summary.errors.append(f"{video.id}: {exc}")
                continue
            summary.videos_upserted += 1
            summary.comments_upserted += comment_count
            summary.thumbnails_upserted += int(thumbnail_upserted)
            if thumbnail_error is not None:
                summary.errors.append(f"{video.id}: thumbnail failed: {thumbnail_error}")

    with session_scope() as session:
        channel_row = session.get(Channel, channel.id)
        if channel_row is not None:
            channel_row.last_ingested_at = datetime.now(UTC)

    return summary
