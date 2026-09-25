"""Phase 1 orchestration: resolve a channel, ingest its videos/comments/thumbnails, upsert.

One video's failure (deleted, comments disabled and something else also going wrong,
extraction failure, ...) is logged and skipped rather than aborting the whole run.
"""

import logging
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


def ingest_channel(settings: Settings, id_or_handle: str) -> IngestSummary:
    summary = IngestSummary()
    youtube = get_youtube_client(settings)
    s3_client = get_s3_client(settings)
    ensure_bucket(s3_client, settings.s3_bucket_thumbnails)

    channel = resolve_channel(youtube, id_or_handle)
    summary.channel_id = channel.id
    with session_scope() as session:
        upsert_channel(session, channel)

    video_ids = list(iter_playlist_video_ids(youtube, channel.uploads_playlist_id))
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
