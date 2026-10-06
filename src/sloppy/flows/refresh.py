"""Prefect flow: wraps ingest -> features -> score into one orchestrated, retryable
per-channel refresh, plus a parent flow that runs it for every channel in
data/seed_channels.csv - Phase 2's labeling-corpus file, reused as Phase 7's
"tracked channels" list per the decision confirmed with the user, rather than
introducing a second, separate list of channels to maintain.
"""

import csv
from pathlib import Path

from prefect import flow, task

from sloppy.config import get_settings
from sloppy.features.pipeline import compute_nlp_features, compute_vision_features
from sloppy.refresh import (
    channel_video_ids,
    ingest_channel_sampled,
    score_with_active_model,
)

DEFAULT_SEED_CHANNELS_CSV = Path("data/seed_channels.csv")


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def ingest_channel_task(id_or_handle: str) -> str:
    """Returns the resolved channel id (ingest_channel resolves a handle to one)."""
    settings = get_settings()
    # Capped (default random sample), never a channel's whole history - see refresh.py.
    summary = ingest_channel_sampled(settings, id_or_handle)
    print(
        f"Ingested channel {summary.channel_id}: {summary.videos_upserted} video(s), "
        f"{summary.comments_upserted} comment(s), {summary.thumbnails_upserted} thumbnail(s), "
        f"{len(summary.errors)} error(s)"
    )
    if summary.channel_id is None:
        raise ValueError(f"ingest_channel did not resolve a channel id for {id_or_handle!r}")
    return summary.channel_id


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def compute_nlp_task(channel_id: str) -> list[str]:
    processed = compute_nlp_features(channel_id=channel_id, only_missing=True)
    print(f"Computed NLP features for {len(processed)} video(s) in {channel_id}")
    return [video_id for video_id, _ in processed]


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def compute_vision_task(channel_id: str) -> list[str]:
    settings = get_settings()
    processed = compute_vision_features(settings, channel_id=channel_id, only_missing=True)
    print(f"Computed vision features for {len(processed)} video(s) in {channel_id}")
    return processed


@task(retries=2, retry_delay_seconds=30, log_prints=True)
def score_channel_task(channel_id: str) -> list[str]:
    settings = get_settings()
    scored, skipped = score_with_active_model(settings, channel_video_ids(channel_id))
    if skipped is not None:
        print(f"Skipping scoring for {channel_id}: {skipped}")
        return []

    print(f"Scored {len(scored)} video(s) in {channel_id}")
    return scored


@flow(name="refresh-channel", log_prints=True)
def refresh_channel_flow(id_or_handle: str) -> dict:
    """Ingest -> compute-nlp -> compute-vision -> score for one channel, strictly in
    sequence - each step depends on the previous one's data existing (there's nothing to
    compute NLP features for until videos are ingested), so this is intentionally not
    parallelized.
    """
    channel_id = ingest_channel_task(id_or_handle)
    nlp_processed = compute_nlp_task(channel_id)
    vision_processed = compute_vision_task(channel_id)
    scored = score_channel_task(channel_id)
    return {
        "channel_id": channel_id,
        "nlp_processed": len(nlp_processed),
        "vision_processed": len(vision_processed),
        "scored": len(scored),
    }


def _load_tracked_channel_handles(csv_path: Path) -> list[str]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [row["handle"] for row in rows if row.get("handle")]


@flow(name="refresh-all-tracked-channels", log_prints=True)
def refresh_all_tracked_channels_flow(
    seed_channels_csv: Path = DEFAULT_SEED_CHANNELS_CSV,
) -> list[dict]:
    """Runs refresh_channel_flow once per channel handle in data/seed_channels.csv, as
    subflows, sequentially - channel ingestion is YouTube-quota-bound, so running many
    channels concurrently wouldn't actually finish faster, just burn through the daily
    quota faster.
    """
    handles = _load_tracked_channel_handles(seed_channels_csv)
    if not handles:
        print(f"No tracked channels found in {seed_channels_csv} - nothing to refresh.")
        return []

    return [refresh_channel_flow(handle) for handle in handles]
