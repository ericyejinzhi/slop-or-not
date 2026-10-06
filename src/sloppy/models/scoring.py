"""Score already-ingested, unlabeled videos with an existing trained model artifact -
the "score" half of Phase 7's ingest -> features -> score refresh flow.

Training (fitting a NEW model) only happens occasionally, via `slop model
train`/`ablation`, over labeled data. A daily orchestrated refresh has no labels for
newly-ingested videos and no product need for any - it should apply whichever model is
already trained. Nothing before this module could do that: `assemble_dataset` requires a
splits.csv entry per video, and `train_model`/`score_dataframe` only ever ran against
freshly-fit models, never a previously-saved artifact loaded back from disk.
"""

import json
from pathlib import Path

import joblib
import pandas as pd

from sloppy.db.session import session_scope
from sloppy.features.dataset import assemble_features_for_video_ids
from sloppy.models.scores import upsert_video_score

SCORE_THRESHOLD = 0.5


def score_videos(
    video_ids: list[str],
    model_name: str,
    model_version: str,
    artifacts_dir: Path,
    split: str = "live",
) -> list[str]:
    """Load the model.joblib artifact for (model_name, model_version), score the given
    video ids, and upsert into video_scores under that exact model_name/version. Returns
    the video ids actually scored - a video_id with no matching Video row is silently
    skipped, matching assemble_features_for_video_ids' own handling of that case.
    """
    model_dir = artifacts_dir / model_name / model_version
    pipeline = joblib.load(model_dir / "model.joblib")
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    all_features = metadata["features"]

    with session_scope() as session:
        df = assemble_features_for_video_ids(session, video_ids)
    if df.empty:
        return []

    probabilities = pipeline.predict_proba(df[all_features])
    down_index = list(pipeline.classes_).index(1)
    scores = pd.Series(probabilities[:, down_index], index=df.index)

    scored_ids: list[str] = []
    with session_scope() as session:
        for idx, row in df.iterrows():
            score = float(scores[idx])
            predicted_label = "down" if score >= SCORE_THRESHOLD else "up"
            upsert_video_score(
                session,
                video_id=row["video_id"],
                model_name=model_name,
                model_version=model_version,
                score=score,
                predicted_label=predicted_label,
                split=split,
                preserve_split=True,
            )
            scored_ids.append(row["video_id"])

    return scored_ids
