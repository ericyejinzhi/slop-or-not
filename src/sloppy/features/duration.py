"""Video-length features. Pure stdlib (statistics module) - deterministic, never needs
real data to test."""

import math
from statistics import mean, pstdev

SHORT_MAX_SECONDS = 180
LONG_MIN_SECONDS = 1200


def duration_bucket(duration_seconds: int | None) -> str:
    if duration_seconds is None:
        return "unknown"
    if duration_seconds <= SHORT_MAX_SECONDS:
        return "short"
    if duration_seconds >= LONG_MIN_SECONDS:
        return "long"
    return "mid"


def duration_deviation(
    duration_seconds: int | None,
    peer_durations: list[int],
    use_log: bool = True,
) -> float | None:
    """Z-score of duration_seconds against a peer group (e.g. the video's channel or
    genre). use_log computes the z-score in log1p-space by default - durations are
    heavy-tailed, so a single multi-hour outlier shouldn't swamp linear-space stats.

    peer_durations is expected to include the video's own duration (a deliberate
    simplification - negligible effect at realistic channel/genre sizes, and much
    simpler/more robust to test than leave-one-out, which breaks on duration ties).

    Returns None if duration_seconds is None or fewer than 2 peers are available.
    """
    if duration_seconds is None or len(peer_durations) < 2:
        return None

    if use_log:
        values = [math.log1p(d) for d in peer_durations]
        target = math.log1p(duration_seconds)
    else:
        values = list(peer_durations)
        target = duration_seconds

    spread = pstdev(values)
    if spread == 0:
        return 0.0
    return (target - mean(values)) / spread
