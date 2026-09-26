from datetime import UTC, datetime, timedelta

import pandas as pd

from sloppy.db.models import Channel, Label, Video, VideoNlpFeatures, VideoVisionFeatures
from sloppy.db.session import session_scope
from sloppy.features.dataset import assemble_dataset, load_splits
from sloppy.features.nlp_store import upsert_video_nlp_features
from sloppy.features.vision_store import upsert_video_vision_features
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.label.labels import record_label

TEST_CHANNEL_ID = "UC_test_dataset_channel"
TEST_VIDEO_PREFIX = "test_dataset_video_"


def _cleanup() -> None:
    with session_scope() as session:
        video_ids = [
            row[0] for row in session.query(Video.id).filter(Video.channel_id == TEST_CHANNEL_ID)
        ]
        session.query(VideoNlpFeatures).filter(VideoNlpFeatures.video_id.in_(video_ids)).delete(
            synchronize_session=False
        )
        session.query(VideoVisionFeatures).filter(
            VideoVisionFeatures.video_id.in_(video_ids)
        ).delete(synchronize_session=False)
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Video).filter(Video.channel_id == TEST_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def test_load_splits_parses_csv(tmp_path):
    csv_path = tmp_path / "splits.csv"
    csv_path.write_text(
        "video_id,channel_id,label,split\nv1,c1,up,train\nv2,c1,down,test\n", encoding="utf-8"
    )
    splits = load_splits(csv_path)
    assert splits == {
        "v1": ("c1", "up", "train"),
        "v2": ("c1", "down", "test"),
    }


def test_assemble_dataset_builds_one_row_per_labeled_video(tmp_path):
    _cleanup()
    try:
        base = datetime.now(UTC)
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )
            for i in range(4):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{TEST_VIDEO_PREFIX}{i}",
                        channel_id=TEST_CHANNEL_ID,
                        title=f"Video {i}" if i != 0 else "YOU WON'T BELIEVE THIS!!!",
                        published_at=base - timedelta(days=i * 3),
                        duration_seconds=500 + i * 50,
                        view_count=1000,
                        like_count=100,
                        comment_count=10,
                    ),
                )

        with session_scope() as session:
            record_label(session, video_id=f"{TEST_VIDEO_PREFIX}0", labeler="t", label="down")
            record_label(session, video_id=f"{TEST_VIDEO_PREFIX}1", labeler="t", label="up")
            # video 2 and 3 are ingested but NOT in splits.csv - should not appear in dataset

        csv_path = tmp_path / "splits.csv"
        csv_path.write_text(
            "video_id,channel_id,label,split\n"
            f"{TEST_VIDEO_PREFIX}0,{TEST_CHANNEL_ID},down,train\n"
            f"{TEST_VIDEO_PREFIX}1,{TEST_CHANNEL_ID},up,train\n",
            encoding="utf-8",
        )
        splits = load_splits(csv_path)

        with session_scope() as session:
            df = assemble_dataset(session, splits)

        assert len(df) == 2
        assert set(df["video_id"]) == {f"{TEST_VIDEO_PREFIX}0", f"{TEST_VIDEO_PREFIX}1"}

        row0 = df[df["video_id"] == f"{TEST_VIDEO_PREFIX}0"].iloc[0]
        assert row0["label"] == "down"
        assert row0["y"] == 1
        assert row0["split"] == "train"
        assert row0["title_caps_ratio"] == 1.0  # "YOU WON'T BELIEVE THIS!!!" is all caps

        row1 = df[df["video_id"] == f"{TEST_VIDEO_PREFIX}1"].iloc[0]
        assert row1["label"] == "up"
        assert row1["y"] == 0
        # corpus stats (used for duration_deviation_channel) should reflect ALL 4 ingested
        # videos, not just the 2 labeled ones
        assert row1["duration_deviation_channel"] is not None
    finally:
        _cleanup()


def test_assemble_dataset_wires_nlp_vision_and_degrades_gracefully_without_them(tmp_path):
    _cleanup()
    try:
        base = datetime.now(UTC)
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
            )
            for i in range(2):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{TEST_VIDEO_PREFIX}{i}",
                        channel_id=TEST_CHANNEL_ID,
                        title="Some Title",
                        published_at=base - timedelta(days=i * 3),
                        duration_seconds=600,
                        view_count=1000,
                        like_count=100,
                        comment_count=10,
                    ),
                )

        # video 0 gets real NLP + vision features processed; video 1 does not (the
        # realistic case for a video not yet run through compute-nlp/compute-vision).
        with session_scope() as session:
            upsert_video_nlp_features(
                session,
                video_id=f"{TEST_VIDEO_PREFIX}0",
                comment_count_scored=5,
                sentiment_mean=0.4,
                sentiment_std=0.1,
                sentiment_negative_share=0.2,
                slop_keyword_rate=0.0,
                topic_cluster_count=3,
                topic_top_cluster_share=0.5,
                topic_top_cluster_sentiment=0.3,
                topic_sentiment_spread=0.1,
                title_lure_score=0.8,
                title_mysterious_score=0.2,
                title_transparent_score=0.1,
                title_embedding=[0.1] * 384,
                description_embedding=None,
                comment_embedding_mean=[0.1] * 384,
                sentiment_model="test",
                embedding_model="test",
            )
            upsert_video_vision_features(
                session,
                video_id=f"{TEST_VIDEO_PREFIX}0",
                image_embedding=[0.1] * 512,
                clip_clickbait_score=0.6,
                clip_ai_generated_score=0.1,
                clip_text_heavy_score=0.2,
                clip_model="test",
            )
            record_label(session, video_id=f"{TEST_VIDEO_PREFIX}0", labeler="t", label="down")
            record_label(session, video_id=f"{TEST_VIDEO_PREFIX}1", labeler="t", label="up")

        csv_path = tmp_path / "splits.csv"
        csv_path.write_text(
            "video_id,channel_id,label,split\n"
            f"{TEST_VIDEO_PREFIX}0,{TEST_CHANNEL_ID},down,train\n"
            f"{TEST_VIDEO_PREFIX}1,{TEST_CHANNEL_ID},up,train\n",
            encoding="utf-8",
        )
        splits = load_splits(csv_path)

        with session_scope() as session:
            df = assemble_dataset(session, splits)

        row0 = df[df["video_id"] == f"{TEST_VIDEO_PREFIX}0"].iloc[0]
        assert row0["sentiment_mean"] == 0.4
        assert row0["title_lure_score"] == 0.8
        assert row0["clip_clickbait_score"] == 0.6
        # lure_score_x_genre: 0.8 >= LURE_HIGH_THRESHOLD (0.5) -> "high"
        assert row0["lure_score_x_genre"] == f"{row0['genre']}::high"

        row1 = df[df["video_id"] == f"{TEST_VIDEO_PREFIX}1"].iloc[0]
        # pandas coerces a mixed None/float column to NaN (not None) once assembled into
        # a DataFrame - pd.isna() is the correct check here, not `is None`.
        assert pd.isna(row1["sentiment_mean"])
        assert pd.isna(row1["title_lure_score"])
        assert pd.isna(row1["clip_clickbait_score"])
        assert pd.isna(row1["lure_score_x_genre"])  # graceful degradation, no crash
    finally:
        _cleanup()
