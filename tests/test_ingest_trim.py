"""Integration tests against the real dev Postgres + MinIO (docker compose up -d).

Uses synthetic throwaway fixture channels/videos only - never the real 34-channel corpus.
Trimming the real corpus is a separate, explicitly-confirmed manual step (see
docs/writeups/TODO.md), not something a test suite run should ever do.
"""

from datetime import UTC, datetime

from sloppy.config import get_settings
from sloppy.db.models import (
    Channel,
    Comment,
    Label,
    Thumbnail,
    Video,
    VideoNlpFeatures,
    VideoScore,
    VideoVisionFeatures,
)
from sloppy.db.session import session_scope
from sloppy.ingest.trim import trim_channel_to_sample
from sloppy.label.labels import record_label
from sloppy.storage import ensure_bucket, get_s3_client

TEST_CHANNEL_ID = "UC_test_ingest_trim_channel"
TEST_VIDEO_PREFIX = "test_ingest_trim_video_"
TEST_BUCKET_PREFIX = "test-ingest-trim/"


def _video_id(i: int) -> str:
    return f"{TEST_VIDEO_PREFIX}{i}"


def _s3_key(i: int) -> str:
    return f"{TEST_BUCKET_PREFIX}{i}.jpg"


def _cleanup() -> None:
    settings = get_settings()
    s3_client = get_s3_client(settings)
    for i in range(10):
        try:
            s3_client.delete_object(Bucket=settings.s3_bucket_thumbnails, Key=_s3_key(i))
        except Exception:  # noqa: BLE001 - best-effort cleanup, object may not exist
            pass
    with session_scope() as session:
        video_ids = [_video_id(i) for i in range(10)]
        session.query(Comment).filter(Comment.video_id.in_(video_ids)).delete(
            synchronize_session=False
        )
        session.query(Thumbnail).filter(Thumbnail.video_id.in_(video_ids)).delete(
            synchronize_session=False
        )
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(VideoScore).filter(VideoScore.video_id.in_(video_ids)).delete(
            synchronize_session=False
        )
        session.query(VideoNlpFeatures).filter(VideoNlpFeatures.video_id.in_(video_ids)).delete(
            synchronize_session=False
        )
        session.query(VideoVisionFeatures).filter(
            VideoVisionFeatures.video_id.in_(video_ids)
        ).delete(synchronize_session=False)
        session.query(Video).filter(Video.id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _seed(count: int) -> None:
    settings = get_settings()
    s3_client = get_s3_client(settings)
    ensure_bucket(s3_client, settings.s3_bucket_thumbnails)

    with session_scope() as session:
        session.add(
            Channel(
                id=TEST_CHANNEL_ID,
                handle="@trimtest",
                title="Trim Test Channel",
                uploads_playlist_id="UU_x",
            )
        )
        # Flushed per video, not batched at the end - this project has no ORM
        # relationship() anywhere (every join is manual), so SQLAlchemy's flush has no
        # dependency info between plain FK-only mapped classes and won't order a child
        # table's inserts after its parent's on its own.
        session.flush()
        for i in range(count):
            video_id = _video_id(i)
            session.add(
                Video(
                    id=video_id,
                    channel_id=TEST_CHANNEL_ID,
                    title=f"Video {i}",
                    published_at=datetime.now(UTC),
                )
            )
            session.flush()
            session.add(
                Comment(
                    id=f"{video_id}_comment",
                    video_id=video_id,
                    text="a comment",
                    published_at=datetime.now(UTC),
                )
            )
            key = _s3_key(i)
            s3_client.put_object(
                Bucket=settings.s3_bucket_thumbnails, Key=key, Body=b"fake-thumbnail-bytes"
            )
            session.add(
                Thumbnail(
                    video_id=video_id,
                    s3_bucket=settings.s3_bucket_thumbnails,
                    s3_key=key,
                    content_type="image/jpeg",
                    source_url="https://example.com/thumb.jpg",
                    downloaded_at=datetime.now(UTC),
                )
            )
            session.add(
                VideoNlpFeatures(
                    video_id=video_id,
                    comment_count_scored=1,
                    sentiment_model="test-model",
                    embedding_model="test-model",
                )
            )
            session.add(VideoVisionFeatures(video_id=video_id, clip_model="test-model"))
            session.add(
                VideoScore(
                    video_id=video_id,
                    model_name="test-model",
                    model_version="v1",
                    score=0.5,
                    predicted_label="up",
                    split="train",
                )
            )


def test_trim_channel_to_sample_keeps_exactly_keep_videos_and_deletes_the_rest():
    _cleanup()
    try:
        _seed(10)
        settings = get_settings()
        s3_client = get_s3_client(settings)

        with session_scope() as session:
            deleted = trim_channel_to_sample(session, s3_client, TEST_CHANNEL_ID, keep=3, seed=42)

        assert deleted == 7
        with session_scope() as session:
            remaining = session.query(Video.id).filter(Video.channel_id == TEST_CHANNEL_ID).all()
        remaining_ids = {row.id for row in remaining}
        assert len(remaining_ids) == 3

        for i in range(10):
            video_id = _video_id(i)
            with session_scope() as session:
                comment_exists = (
                    session.query(Comment).filter(Comment.video_id == video_id).first() is not None
                )
                thumbnail_exists = (
                    session.query(Thumbnail).filter(Thumbnail.video_id == video_id).first()
                    is not None
                )
                nlp_exists = (
                    session.query(VideoNlpFeatures)
                    .filter(VideoNlpFeatures.video_id == video_id)
                    .first()
                    is not None
                )
                vision_exists = (
                    session.query(VideoVisionFeatures)
                    .filter(VideoVisionFeatures.video_id == video_id)
                    .first()
                    is not None
                )
                score_exists = (
                    session.query(VideoScore).filter(VideoScore.video_id == video_id).first()
                    is not None
                )
            s3_exists = True
            try:
                s3_client.head_object(Bucket=settings.s3_bucket_thumbnails, Key=_s3_key(i))
            except Exception:  # noqa: BLE001 - head_object raises ClientError when missing
                s3_exists = False

            if video_id in remaining_ids:
                assert comment_exists and thumbnail_exists and nlp_exists
                assert vision_exists and score_exists and s3_exists
            else:
                assert not any(
                    (comment_exists, thumbnail_exists, nlp_exists, vision_exists, score_exists)
                )
                assert not s3_exists
    finally:
        _cleanup()


def test_trim_channel_to_sample_is_a_noop_when_already_at_or_below_keep():
    _cleanup()
    try:
        _seed(3)
        settings = get_settings()
        s3_client = get_s3_client(settings)

        with session_scope() as session:
            deleted = trim_channel_to_sample(session, s3_client, TEST_CHANNEL_ID, keep=10)

        assert deleted == 0
        with session_scope() as session:
            count = session.query(Video).filter(Video.channel_id == TEST_CHANNEL_ID).count()
        assert count == 3
    finally:
        _cleanup()


def test_trim_channel_to_sample_never_deletes_an_already_labeled_video():
    """Real usage found this gap directly: the dev DB started accumulating real labels
    from actual use of the labeling page while this trim feature was still mid-build.
    Trimming must never silently discard a video someone already judged, even if the
    random sample wouldn't otherwise have kept it - labeled videos are always kept,
    which can mean keeping MORE than `keep` total.
    """
    _cleanup()
    try:
        _seed(10)
        with session_scope() as session:
            # Pin a label to a specific, otherwise-arbitrary video so this test doesn't
            # depend on randomness also happening to keep it.
            record_label(session, video_id=_video_id(7), labeler="t", label="down")

        settings = get_settings()
        s3_client = get_s3_client(settings)
        with session_scope() as session:
            trim_channel_to_sample(session, s3_client, TEST_CHANNEL_ID, keep=3, seed=1)

        with session_scope() as session:
            remaining = {
                row.id
                for row in session.query(Video.id).filter(Video.channel_id == TEST_CHANNEL_ID)
            }
            label_still_exists = (
                session.query(Label).filter(Label.video_id == _video_id(7)).first() is not None
            )
        assert _video_id(7) in remaining
        assert label_still_exists
        # keep=3 total: the 1 labeled video is always kept, plus (3 - 1) = 2 randomly
        # sampled unlabeled ones.
        assert len(remaining) == 3
    finally:
        _cleanup()
