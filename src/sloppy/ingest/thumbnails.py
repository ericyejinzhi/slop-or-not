"""Thumbnail extraction (yt-dlp, metadata-only) and upload to MinIO/S3."""

import urllib.request

import yt_dlp
from pydantic import BaseModel

from sloppy.config import Settings


class ThumbnailInfo(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None


def _pick_best_thumbnail(thumbnails: list[dict]) -> dict:
    sized = [t for t in thumbnails if t.get("width") and t.get("height")]
    if not sized:
        raise ValueError("No thumbnail with known dimensions available")
    return max(sized, key=lambda t: t["width"] * t["height"])


def extract_thumbnail_url(video_id: str) -> ThumbnailInfo:
    """Extract the highest-resolution thumbnail URL via yt-dlp, without downloading the video."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(watch_url, download=False)

    best = _pick_best_thumbnail(info.get("thumbnails", []))
    return ThumbnailInfo(url=best["url"], width=best.get("width"), height=best.get("height"))


def download_thumbnail_bytes(url: str) -> tuple[bytes, str]:
    with urllib.request.urlopen(url) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type", "image/jpeg")
    return content, content_type


def upload_thumbnail(
    s3_client, settings: Settings, video_id: str, content: bytes, content_type: str
) -> str:
    key = f"{video_id}.jpg"
    s3_client.put_object(
        Bucket=settings.s3_bucket_thumbnails,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return key
