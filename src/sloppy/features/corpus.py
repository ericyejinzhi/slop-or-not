"""Corpus-wide aggregates (per-channel and per-genre peer groups, upload cadence).

Operates on anything with the right attributes (a VideoLike protocol) - satisfied
directly by ORM Video rows, and by small synthetic dataclasses in tests without
touching the DB.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Protocol


class VideoLike(Protocol):
    id: str
    channel_id: str
    duration_seconds: int | None
    published_at: datetime
    topic_categories: list[str] | None


def primary_genre(topic_categories: list[str] | None) -> str:
    """Last path segment of the first topic URL (matches the display idiom already used
    in cli.py's `t.rsplit("/", 1)[-1]`). A video can have multiple topic_categories;
    using the first as "primary genre" for grouping is a deliberate simplification."""
    if not topic_categories:
        return "unknown"
    return topic_categories[0].rsplit("/", 1)[-1] or "unknown"


def upload_cadence_days(published_dates: list[datetime]) -> float | None:
    """Median inter-arrival gap (in days) across a channel's sorted published_at values.
    Uses the WHOLE channel's upload history (not just videos published before this one) -
    a documented, acceptable leakage simplification for a baseline model."""
    if len(published_dates) < 2:
        return None
    ordered = sorted(published_dates)
    # strict=False: pairing a list against its own tail is intentionally length-N vs N-1.
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(ordered, ordered[1:], strict=False)]
    return median(gaps)


@dataclass
class CorpusStats:
    durations_by_channel: dict[str, list[int]] = field(default_factory=dict)
    durations_by_genre: dict[str, list[int]] = field(default_factory=dict)
    published_dates_by_channel: dict[str, list[datetime]] = field(default_factory=dict)


def build_corpus_stats(videos: list[VideoLike]) -> CorpusStats:
    durations_by_channel: dict[str, list[int]] = defaultdict(list)
    durations_by_genre: dict[str, list[int]] = defaultdict(list)
    published_dates_by_channel: dict[str, list[datetime]] = defaultdict(list)

    for video in videos:
        published_dates_by_channel[video.channel_id].append(video.published_at)
        if video.duration_seconds is not None:
            durations_by_channel[video.channel_id].append(video.duration_seconds)
            genre = primary_genre(video.topic_categories)
            durations_by_genre[genre].append(video.duration_seconds)

    return CorpusStats(
        durations_by_channel=dict(durations_by_channel),
        durations_by_genre=dict(durations_by_genre),
        published_dates_by_channel=dict(published_dates_by_channel),
    )
