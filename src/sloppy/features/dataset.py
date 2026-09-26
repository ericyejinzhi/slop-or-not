"""Assembles a training-ready DataFrame: splits.csv + all ingested videos (for corpus
norms) + per-video metadata/NLP/vision/similarity/interaction features, one row per
labeled video. Missing NLP/vision rows (a video not yet processed by `slop features
compute-nlp`/`compute-vision`) degrade gracefully to None - SimpleImputer/OneHotEncoder
already handle that downstream without new preprocessing code.
"""

import csv
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from sloppy.db.models import Video, VideoNlpFeatures, VideoVisionFeatures
from sloppy.features.corpus import build_corpus_stats
from sloppy.features.extract import extract_features
from sloppy.features.interactions import (
    duration_deviation_x_cadence,
    lure_score_x_genre,
    mysterious_score_x_duration_bucket,
)
from sloppy.features.sentiment import channel_sentiment_rollup
from sloppy.features.similarity import (
    channel_thumbnail_self_similarity_mean,
    channel_title_self_similarity_mean,
    near_duplicate_thumbnail_count,
)

_NLP_SCALAR_COLUMNS = (
    "sentiment_mean",
    "sentiment_std",
    "sentiment_negative_share",
    "slop_keyword_rate",
    "topic_cluster_count",
    "topic_top_cluster_share",
    "topic_top_cluster_sentiment",
    "topic_sentiment_spread",
    "title_lure_score",
    "title_mysterious_score",
    "title_transparent_score",
)
_VISION_SCALAR_COLUMNS = (
    "clip_clickbait_score",
    "clip_ai_generated_score",
    "clip_text_heavy_score",
)


def load_splits(csv_path: Path) -> dict[str, tuple[str, str, str]]:
    """video_id -> (channel_id, label, split)."""
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {row["video_id"]: (row["channel_id"], row["label"], row["split"]) for row in rows}


def assemble_dataset(session: Session, splits: dict[str, tuple[str, str, str]]) -> pd.DataFrame:
    """One row per video_id in `splits`. Corpus stats and the channel sentiment rollup
    are built from ALL ingested/processed videos, not just the labeled subset - those
    norms should reflect the real corpus, not be skewed by which videos got labeled.
    """
    all_videos = list(session.execute(select(Video)).scalars())
    corpus = build_corpus_stats(all_videos)
    videos_by_id = {v.id: v for v in all_videos}
    channel_by_video_all = {v.id: v.channel_id for v in all_videos}

    nlp_by_video = {f.video_id: f for f in session.execute(select(VideoNlpFeatures)).scalars()}
    vision_by_video = {
        f.video_id: f for f in session.execute(select(VideoVisionFeatures)).scalars()
    }

    video_sentiment_means = {
        video_id: f.sentiment_mean
        for video_id, f in nlp_by_video.items()
        if f.sentiment_mean is not None
    }
    channel_sentiment = channel_sentiment_rollup(video_sentiment_means, channel_by_video_all)

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

        nlp = nlp_by_video.get(video_id)
        for col in _NLP_SCALAR_COLUMNS:
            record[col] = getattr(nlp, col) if nlp is not None else None

        vision = vision_by_video.get(video_id)
        for col in _VISION_SCALAR_COLUMNS:
            record[col] = getattr(vision, col) if vision is not None else None

        record["channel_sentiment_mean"] = channel_sentiment.get(channel_id)
        record["channel_thumbnail_self_similarity"] = channel_thumbnail_self_similarity_mean(
            session, video_id, channel_id
        )
        record["near_duplicate_thumbnail_count"] = near_duplicate_thumbnail_count(session, video_id)
        record["channel_title_self_similarity"] = channel_title_self_similarity_mean(
            session, video_id, channel_id
        )

        record["lure_score_x_genre"] = lure_score_x_genre(
            record["title_lure_score"], record["genre"]
        )
        record["duration_deviation_x_cadence"] = duration_deviation_x_cadence(
            record["duration_deviation_genre"], record["channel_upload_cadence_days"]
        )
        record["mysterious_score_x_duration_bucket"] = mysterious_score_x_duration_bucket(
            record["title_mysterious_score"], record["duration_bucket"]
        )

        records.append(record)

    return pd.DataFrame.from_records(records)
