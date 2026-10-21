"""Turn whatever a visitor pastes into a YouTube video id."""

import re
from urllib.parse import parse_qs, urlparse

from sloppy.predict.errors import InvalidVideoLink

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
# /shorts/<id>, /embed/<id>, /live/<id>, /v/<id>
_PATH_PREFIXES = ("shorts", "embed", "live", "v")


def parse_video_id(text: str) -> str:
    """Accepts a watch, short (youtu.be), Shorts, embed or live URL, or a bare 11-character
    video id. Raises InvalidVideoLink for anything else - including playlist, channel and
    handle URLs, which name no single video."""
    candidate = (text or "").strip()
    if not candidate:
        raise InvalidVideoLink("Paste a YouTube video link.")
    if _VIDEO_ID_RE.match(candidate):
        return candidate

    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()

    video_id: str | None = None
    if parsed.scheme not in ("http", "https"):
        video_id = None
    elif host in _SHORT_HOSTS:
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif host in _YOUTUBE_HOSTS:
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0] == "watch":
            video_id = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(parts) >= 2 and parts[0] in _PATH_PREFIXES:
            video_id = parts[1]

    if video_id is None or not _VIDEO_ID_RE.match(video_id):
        raise InvalidVideoLink(
            "That does not look like a link to a single YouTube video "
            "(try the address from the video's page or its Share button)."
        )
    return video_id
