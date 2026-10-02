"""Trims an already-ingested channel down to a random subset of its videos.

Needed because the channel-batch labeling methodology (see docs/writeups/TODO.md) samples
a small, fixed number of videos per channel - channels ingested earlier under the old
most-recent-N methodology (or an earlier, larger sample size) can have more videos on
disk than the new methodology wants to carry forward.

No FK in src/sloppy/db/models.py cascades on delete (confirmed directly against the
models), so every child row referencing a video - comments, thumbnails, labels,
video_scores, video_nlp_features, video_vision_features - must be deleted before the
video row itself, or Postgres raises an FK violation. The real S3/MinIO thumbnail object
is also deleted, not just its DB row, so trimming actually frees disk space.
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from sloppy.db.models import (
    Comment,
    Label,
    Thumbnail,
    Video,
    VideoNlpFeatures,
    VideoScore,
    VideoVisionFeatures,
)

_CHILD_MODELS = (Comment, Thumbnail, Label, VideoScore, VideoNlpFeatures, VideoVisionFeatures)


def trim_channel_to_sample(
    session: Session,
    s3_client,
    channel_id: str,
    keep: int,
    seed: int | None = None,
) -> int:
    """Randomly keeps `keep` of the channel's currently-ingested videos, deleting
    everything else (and every row referencing a deleted video). Returns how many videos
    were deleted - 0 if the channel already has `keep` or fewer videos (a no-op, not an
    error, since "nothing to trim" is a perfectly normal outcome for a freshly-sampled
    channel).

    Already-labeled videos are NEVER deleted, even if that means keeping more than
    `keep` total - trimming exists to shrink an over-sized candidate pool, not to discard
    real human judgments. If a channel has more labeled videos than `keep`, every
    labeled one is kept and nothing is randomly sampled on top.
    """
    video_ids = list(
        session.execute(select(Video.id).where(Video.channel_id == channel_id)).scalars()
    )
    if len(video_ids) <= keep:
        return 0

    labeled_ids = set(
        session.execute(select(Label.video_id).where(Label.video_id.in_(video_ids))).scalars()
    )
    unlabeled_ids = [video_id for video_id in video_ids if video_id not in labeled_ids]

    remaining_slots = max(keep - len(labeled_ids), 0)
    sample_size = min(remaining_slots, len(unlabeled_ids))
    kept = labeled_ids | set(random.Random(seed).sample(unlabeled_ids, sample_size))
    to_delete = [video_id for video_id in video_ids if video_id not in kept]
    if not to_delete:
        return 0

    thumbnails = session.execute(
        select(Thumbnail).where(Thumbnail.video_id.in_(to_delete))
    ).scalars()
    for thumbnail in thumbnails:
        s3_client.delete_object(Bucket=thumbnail.s3_bucket, Key=thumbnail.s3_key)

    for model in _CHILD_MODELS:
        session.query(model).filter(model.video_id.in_(to_delete)).delete(synchronize_session=False)
    session.query(Video).filter(Video.id.in_(to_delete)).delete(synchronize_session=False)

    return len(to_delete)
