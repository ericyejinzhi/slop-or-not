"""YouTube Data API v3 client: channel resolution, video metadata (Stage 2), comments (Stage 3)."""

import logging
import re
import time
from collections.abc import Callable, Iterator
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

from sloppy.config import Settings

logger = logging.getLogger(__name__)

_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
_DURATION_RE = re.compile(r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$")

_RETRYABLE_STATUSES = {403, 429, 500, 502, 503}


class ChannelMeta(BaseModel):
    id: str
    handle: str | None = None
    title: str
    description: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    view_count: int | None = None
    uploads_playlist_id: str


class VideoMeta(BaseModel):
    id: str
    channel_id: str
    title: str
    description: str | None = None
    published_at: datetime
    duration_seconds: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    topic_categories: list[str] = []
    tags: list[str] = []
    thumbnail_url: str | None = None


def get_youtube_client(settings: Settings):
    # Discovery-doc caching depends on oauth2client, which isn't installed here; disabling it
    # avoids a noisy (harmless) warning on every client build.
    return build("youtube", "v3", developerKey=settings.youtube_api_key, cache_discovery=False)


def _error_reason(exc: HttpError) -> str | None:
    try:
        return exc.error_details[0]["reason"]
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _with_retry[T](fn: Callable[[], T], max_attempts: int = 3, base_delay: float = 1.0) -> T:
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except HttpError as exc:
            reason = _error_reason(exc)
            if reason == "quotaExceeded":
                logger.error("YouTube API quota exceeded")
                raise
            status = exc.resp.status if exc.resp else None
            if attempt == max_attempts or status not in _RETRYABLE_STATUSES:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "YouTube API error (%s), retrying in %.1fs [attempt %d/%d]",
                reason or status,
                delay,
                attempt,
                max_attempts,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def parse_duration(iso: str) -> int | None:
    """Parse an ISO 8601 duration like 'PT1H2M3S' into total seconds."""
    match = _DURATION_RE.match(iso)
    if not match or not iso:
        return None
    parts = match.groupdict()
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    return hours * 3600 + minutes * 60 + seconds


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value is not None else None


def _best_thumbnail_url(thumbnails: dict) -> str | None:
    for key in ("maxres", "standard", "high", "medium", "default"):
        if key in thumbnails:
            return thumbnails[key]["url"]
    return None


def resolve_channel(client, id_or_handle: str) -> ChannelMeta:
    request_kwargs: dict = {"part": "snippet,statistics,contentDetails"}
    if _CHANNEL_ID_RE.match(id_or_handle):
        request_kwargs["id"] = id_or_handle
    else:
        request_kwargs["forHandle"] = id_or_handle.lstrip("@")

    response = _with_retry(lambda: client.channels().list(**request_kwargs).execute())
    items = response.get("items", [])
    if not items:
        raise ValueError(f"No YouTube channel found for {id_or_handle!r}")

    item = items[0]
    snippet = item["snippet"]
    statistics = item.get("statistics", {})
    return ChannelMeta(
        id=item["id"],
        handle=snippet.get("customUrl"),
        title=snippet["title"],
        description=snippet.get("description"),
        subscriber_count=_int_or_none(statistics.get("subscriberCount")),
        video_count=_int_or_none(statistics.get("videoCount")),
        view_count=_int_or_none(statistics.get("viewCount")),
        uploads_playlist_id=item["contentDetails"]["relatedPlaylists"]["uploads"],
    )


def iter_playlist_video_ids(client, playlist_id: str) -> Iterator[str]:
    page_token = None
    while True:
        response = _with_retry(
            lambda pt=page_token: (
                client.playlistItems()
                .list(part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=pt)
                .execute()
            )
        )
        for item in response.get("items", []):
            yield item["contentDetails"]["videoId"]
        page_token = response.get("nextPageToken")
        if not page_token:
            break


def _parse_video(item: dict) -> VideoMeta:
    snippet = item["snippet"]
    statistics = item.get("statistics", {})
    content_details = item.get("contentDetails", {})
    topic_details = item.get("topicDetails", {})
    return VideoMeta(
        id=item["id"],
        channel_id=snippet["channelId"],
        title=snippet["title"],
        description=snippet.get("description"),
        published_at=snippet["publishedAt"],
        duration_seconds=parse_duration(content_details.get("duration", "")),
        view_count=_int_or_none(statistics.get("viewCount")),
        like_count=_int_or_none(statistics.get("likeCount")),
        comment_count=_int_or_none(statistics.get("commentCount")),
        topic_categories=topic_details.get("topicCategories", []),
        tags=snippet.get("tags", []),
        thumbnail_url=_best_thumbnail_url(snippet.get("thumbnails", {})),
    )


def fetch_videos_metadata(client, video_ids: list[str]) -> list[VideoMeta]:
    results: list[VideoMeta] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        response = _with_retry(
            lambda b=batch: (
                client.videos()
                .list(part="snippet,statistics,contentDetails,topicDetails", id=",".join(b))
                .execute()
            )
        )
        results.extend(_parse_video(item) for item in response.get("items", []))
    return results
