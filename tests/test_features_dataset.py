from datetime import UTC, datetime, timedelta

from sloppy.db.models import Channel, Label, Video
from sloppy.db.session import session_scope
from sloppy.features.dataset import assemble_dataset, load_splits
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
