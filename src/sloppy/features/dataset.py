"""Assembles a training-ready DataFrame: splits.csv + all ingested videos (for corpus
norms) + per-video features, one row per labeled video.
"""

import csv
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from sloppy.db.models import Video
from sloppy.features.corpus import build_corpus_stats
from sloppy.features.extract import extract_features


def load_splits(csv_path: Path) -> dict[str, tuple[str, str, str]]:
    """video_id -> (channel_id, label, split)."""
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {row["video_id"]: (row["channel_id"], row["label"], row["split"]) for row in rows}


def assemble_dataset(session: Session, splits: dict[str, tuple[str, str, str]]) -> pd.DataFrame:
    """One row per video_id in `splits`. Corpus stats (channel/genre duration norms,
    upload cadence) are built from ALL ingested videos, not just the labeled subset -
    those norms should reflect the real corpus, not be skewed by which videos happened
    to get labeled.
    """
    all_videos = list(session.execute(select(Video)).scalars())
    corpus = build_corpus_stats(all_videos)
    videos_by_id = {v.id: v for v in all_videos}

    records = []
    for video_id, (channel_id, label, split) in splits.items():
        video = videos_by_id.get(video_id)
        if video is None:
            continue
        features = extract_features(video, corpus)
        record = asdict(features)
        record["channel_id"] = channel_id
        record["label"] = label
        record["y"] = 1 if label == "down" else 0
        record["split"] = split
        records.append(record)

    return pd.DataFrame.from_records(records)
