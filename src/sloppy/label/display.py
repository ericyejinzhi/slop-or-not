"""Thumbnail caching + auto-open during labeling.

cache_thumbnail reads the real s3_bucket/s3_key/content_type from the video's `thumbnails`
row (not re-derived/assumed) - the extension is picked from the actual content_type, not
hardcoded .jpg, since Phase 1 found some thumbnails are WebP bytes under a .jpg S3 key.
"""

import mimetypes
import os
import tempfile
from pathlib import Path

_CACHE_DIR = Path(tempfile.gettempdir()) / "sloppy_label_thumbnails"

# mimetypes.guess_extension() is unreliable for this - e.g. it returns None for
# "image/webp" on this system (stdlib/OS mimetypes registries vary), which would silently
# fall back to ".jpg" and defeat the whole point of deriving the extension from content
# type. Hardcode the handful of formats YouTube thumbnails actually come back as.
_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/png": ".png",
    "image/gif": ".gif",
}


def _extension_for_content_type(content_type: str) -> str:
    return (
        _EXTENSION_BY_CONTENT_TYPE.get(content_type)
        or mimetypes.guess_extension(content_type)
        or ".jpg"
    )


def cache_thumbnail(
    s3_client, video_id: str, s3_bucket: str, s3_key: str, content_type: str
) -> Path:
    """Downloads to a per-video-id local cache file (extension matches content_type).
    Unique filenames, not one fixed overwritten path, because image viewers don't
    reliably auto-refresh a static path's changed bytes. Skips the download if this
    video's thumbnail is already cached from earlier in the session."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    extension = _extension_for_content_type(content_type)
    path = _CACHE_DIR / f"{video_id}{extension}"
    if not path.exists():
        obj = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        path.write_bytes(obj["Body"].read())
    return path


def open_image(path: Path) -> None:
    os.startfile(path)  # noqa: S606 - Windows-only by design; path is our own cache file
