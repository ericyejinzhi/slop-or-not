"""Integration tests against the real dev Postgres (docker compose up -d)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from sloppy.api.app import app
from sloppy.db.models import Channel, Label, Video
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.label.labels import record_label

client = TestClient(app)

TEST_CHANNEL_ID = "UC_test_api_labels_channel"
TEST_VIDEO_ID = "test_api_labels_video_0001"

POOL_CHANNEL_ID = "UC_test_api_labels_pool_channel"
POOL_VIDEO_PREFIX = "test_api_labels_pool_video_"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Label).filter(Label.video_id == TEST_VIDEO_ID).delete()
        session.query(Video).filter(Video.id == TEST_VIDEO_ID).delete()
        session.query(Channel).filter(Channel.id == TEST_CHANNEL_ID).delete()


def _seed_video() -> None:
    with session_scope() as session:
        upsert_channel(
            session,
            ChannelMeta(id=TEST_CHANNEL_ID, title="Test Channel", uploads_playlist_id="UU_x"),
        )
        upsert_video(
            session,
            VideoMeta(
                id=TEST_VIDEO_ID,
                channel_id=TEST_CHANNEL_ID,
                title="Test Video",
                published_at=datetime.now(UTC),
            ),
        )


def test_post_labels_creates_a_row_with_explicit_labeler():
    _cleanup()
    try:
        _seed_video()
        response = client.post(
            "/labels",
            json={
                "video_id": TEST_VIDEO_ID,
                "labeler": "alice",
                "label": "down",
                "notes": "looks like slop",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["video_id"] == TEST_VIDEO_ID
        assert body["labeler"] == "alice"
        assert body["label"] == "down"
        assert body["notes"] == "looks like slop"

        with session_scope() as session:
            rows = session.query(Label).filter(Label.video_id == TEST_VIDEO_ID).all()
            assert len(rows) == 1
            assert rows[0].labeler == "alice"
            assert rows[0].label == "down"
    finally:
        _cleanup()


def test_post_labels_falls_back_to_settings_labeler_name(monkeypatch):
    _cleanup()
    try:
        _seed_video()
        monkeypatch.setenv("LABELER_NAME", "configured-labeler")
        from sloppy.config import get_settings

        get_settings.cache_clear()
        try:
            response = client.post("/labels", json={"video_id": TEST_VIDEO_ID, "label": "up"})
            assert response.status_code == 201
            assert response.json()["labeler"] == "configured-labeler"
        finally:
            get_settings.cache_clear()
    finally:
        _cleanup()


def test_post_labels_400_when_no_labeler_available(monkeypatch):
    _cleanup()
    try:
        _seed_video()
        monkeypatch.setenv("LABELER_NAME", "")
        from sloppy.config import get_settings

        get_settings.cache_clear()
        try:
            response = client.post("/labels", json={"video_id": TEST_VIDEO_ID, "label": "up"})
            assert response.status_code == 400
        finally:
            get_settings.cache_clear()
    finally:
        _cleanup()


def test_post_labels_404_for_nonexistent_video():
    response = client.post(
        "/labels", json={"video_id": "does-not-exist", "labeler": "alice", "label": "up"}
    )
    assert response.status_code == 404


def test_post_labels_422_for_invalid_label_value():
    _cleanup()
    try:
        _seed_video()
        response = client.post(
            "/labels",
            json={"video_id": TEST_VIDEO_ID, "labeler": "alice", "label": "sideways"},
        )
        assert response.status_code == 422
    finally:
        _cleanup()


def _cleanup_pool() -> None:
    with session_scope() as session:
        video_ids = [
            row[0] for row in session.query(Video.id).filter(Video.channel_id == POOL_CHANNEL_ID)
        ]
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Video).filter(Video.channel_id == POOL_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == POOL_CHANNEL_ID).delete()


def test_get_label_pool_excludes_labeled_and_respects_per_channel_max():
    _cleanup_pool()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(
                    id=POOL_CHANNEL_ID,
                    handle="@poolchannel",
                    title="Pool Channel",
                    uploads_playlist_id="UU_x",
                ),
            )
            now = datetime.now(UTC)
            for i in range(5):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{POOL_VIDEO_PREFIX}{i}",
                        channel_id=POOL_CHANNEL_ID,
                        title=f"Pool Video {i}",
                        published_at=now - timedelta(days=i),
                    ),
                )
        with session_scope() as session:
            record_label(session, video_id=f"{POOL_VIDEO_PREFIX}0", labeler="t", label="up")

        response = client.get("/labels/pool", params={"per_channel_max": 2, "pool_size": 100})
        assert response.status_code == 200
        items = response.json()["items"]
        this_channel = [i for i in items if i["channel_id"] == POOL_CHANNEL_ID]
        # candidate_videos ranks by recency FIRST (per_channel_max=2 keeps videos 0 and
        # 1, the 2 most recent), THEN excludes labeled ones from that already-capped set
        # - video 0 is labeled and drops out, leaving only video 1. Video 2 never enters
        # consideration even though it's unlabeled, since it didn't make the rn<=2 cut.
        assert {i["video_id"] for i in this_channel} == {f"{POOL_VIDEO_PREFIX}1"}
        assert all(i["title"].startswith("Pool Video") for i in this_channel)
        assert all(i["channel_handle"] == "@poolchannel" for i in this_channel)
    finally:
        _cleanup_pool()


def test_get_label_pool_consistency_mode_returns_labeled_videos():
    _cleanup_pool()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=POOL_CHANNEL_ID, title="Pool Channel", uploads_playlist_id="UU_x"),
            )
            upsert_video(
                session,
                VideoMeta(
                    id=f"{POOL_VIDEO_PREFIX}0",
                    channel_id=POOL_CHANNEL_ID,
                    title="Pool Video 0",
                    published_at=datetime.now(UTC),
                ),
            )
        with session_scope() as session:
            record_label(session, video_id=f"{POOL_VIDEO_PREFIX}0", labeler="t", label="up")

        # consistency_sample draws an UNSEEDED random sample from every labeled video in
        # the whole table, not just this test's fixture - this dev DB now also holds 100+
        # real labels from actual use of the labeling page, so the default sample size
        # (20) would only sometimes include this test's own video. A huge
        # consistency_sample_size avoids anything being truncated away before it's found.
        response = client.get(
            "/labels/pool", params={"mode": "consistency", "consistency_sample_size": 100_000}
        )
        assert response.status_code == 200
        video_ids = {item["video_id"] for item in response.json()["items"]}
        assert f"{POOL_VIDEO_PREFIX}0" in video_ids
    finally:
        _cleanup_pool()


LIST_CHANNEL_ID = "UC_test_api_labels_list_channel"
LIST_VIDEO_PREFIX = "test_api_labels_list_video_"


def _cleanup_list() -> None:
    with session_scope() as session:
        video_ids = [
            row[0] for row in session.query(Video.id).filter(Video.channel_id == LIST_CHANNEL_ID)
        ]
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Video).filter(Video.channel_id == LIST_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == LIST_CHANNEL_ID).delete()


def test_get_labels_list_shows_most_recent_label_and_count_after_a_relabel():
    _cleanup_list()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(
                    id=LIST_CHANNEL_ID,
                    handle="@listchannel",
                    title="List Channel",
                    uploads_playlist_id="UU_x",
                ),
            )
            upsert_video(
                session,
                VideoMeta(
                    id=f"{LIST_VIDEO_PREFIX}0",
                    channel_id=LIST_CHANNEL_ID,
                    title="Relabeled Video",
                    published_at=datetime.now(UTC),
                ),
            )
        # Separate session_scope blocks (separate transactions), matching how two real
        # POST /labels calls would actually happen - `created_at` uses
        # server_default=func.now(), which returns the TRANSACTION's start time, so
        # putting both in one transaction would give them an identical timestamp.
        with session_scope() as session:
            # First judgment, then a relabel - the list endpoint must reflect the LATEST
            # one (down), not the first (up), while still counting both.
            record_label(session, video_id=f"{LIST_VIDEO_PREFIX}0", labeler="alice", label="up")
        with session_scope() as session:
            record_label(session, video_id=f"{LIST_VIDEO_PREFIX}0", labeler="bob", label="down")

        response = client.get("/labels", params={"q": "Relabeled"})
        assert response.status_code == 200
        body = response.json()
        matches = [item for item in body["items"] if item["video_id"] == f"{LIST_VIDEO_PREFIX}0"]
        assert len(matches) == 1
        item = matches[0]
        assert item["label"] == "down"
        assert item["labeler"] == "bob"
        assert item["label_count"] == 2
        assert item["channel_handle"] == "@listchannel"
    finally:
        _cleanup_list()


def test_get_labels_list_filters_by_label_value():
    _cleanup_list()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=LIST_CHANNEL_ID, title="List Channel", uploads_playlist_id="UU_x"),
            )
            for i, _label_value in enumerate(["up", "down"]):
                upsert_video(
                    session,
                    VideoMeta(
                        id=f"{LIST_VIDEO_PREFIX}{i}",
                        channel_id=LIST_CHANNEL_ID,
                        title=f"Filter Video {i}",
                        published_at=datetime.now(UTC),
                    ),
                )
        with session_scope() as session:
            for i, label_value in enumerate(["up", "down"]):
                record_label(
                    session, video_id=f"{LIST_VIDEO_PREFIX}{i}", labeler="t", label=label_value
                )

        response = client.get("/labels", params={"label": "down", "q": "Filter Video"})
        assert response.status_code == 200
        video_ids = {item["video_id"] for item in response.json()["items"]}
        assert video_ids == {f"{LIST_VIDEO_PREFIX}1"}
    finally:
        _cleanup_list()


def test_get_labels_list_excludes_unlabeled_videos():
    _cleanup_list()
    try:
        with session_scope() as session:
            upsert_channel(
                session,
                ChannelMeta(id=LIST_CHANNEL_ID, title="List Channel", uploads_playlist_id="UU_x"),
            )
            upsert_video(
                session,
                VideoMeta(
                    id=f"{LIST_VIDEO_PREFIX}0",
                    channel_id=LIST_CHANNEL_ID,
                    title="Never Labeled Video",
                    published_at=datetime.now(UTC),
                ),
            )
        response = client.get("/labels", params={"q": "Never Labeled"})
        assert response.status_code == 200
        assert response.json()["items"] == []
    finally:
        _cleanup_list()


BATCH_CHANNEL_ID = "UC_test_api_labels_batch_channel"
BATCH_VIDEO_PREFIX = "test_api_labels_batch_video_"


def _cleanup_batch() -> None:
    with session_scope() as session:
        video_ids = [
            row[0] for row in session.query(Video.id).filter(Video.channel_id == BATCH_CHANNEL_ID)
        ]
        session.query(Label).filter(Label.video_id.in_(video_ids)).delete(synchronize_session=False)
        session.query(Video).filter(Video.channel_id == BATCH_CHANNEL_ID).delete()
        session.query(Channel).filter(Channel.id == BATCH_CHANNEL_ID).delete()


def _seed_batch_channel(n: int) -> list[str]:
    with session_scope() as session:
        upsert_channel(
            session,
            ChannelMeta(
                id=BATCH_CHANNEL_ID,
                handle="@batchchannel",
                title="Batch Channel",
                uploads_playlist_id="UU_x",
            ),
        )
        for i in range(n):
            upsert_video(
                session,
                VideoMeta(
                    id=f"{BATCH_VIDEO_PREFIX}{i}",
                    channel_id=BATCH_CHANNEL_ID,
                    title=f"Batch Video {i}",
                    published_at=datetime.now(UTC),
                ),
            )
    return [f"{BATCH_VIDEO_PREFIX}{i}" for i in range(n)]


def test_get_channel_batch_pool_groups_by_channel_and_excludes_labeled_channels():
    _cleanup_batch()
    try:
        video_ids = _seed_batch_channel(4)

        # Not yet labeled - the channel should appear, with all 4 videos in its batch.
        # pool_size=200 (the max) so our test channel isn't crowded out by the real
        # corpus's other ~34 channels also present in this shared dev DB.
        response = client.get("/labels/channel-pool", params={"pool_size": 200})
        assert response.status_code == 200
        items = response.json()["items"]
        match = [item for item in items if item["channel_id"] == BATCH_CHANNEL_ID]
        assert len(match) == 1
        assert {v["video_id"] for v in match[0]["videos"]} == set(video_ids)
        assert match[0]["channel_handle"] == "@batchchannel"

        # Label just one of its videos - the whole channel should now be excluded, since
        # a channel-batch label applies atomically, so "partially labeled" isn't treated
        # as "still needs labeling".
        with session_scope() as session:
            record_label(session, video_id=video_ids[0], labeler="t", label="up")

        response = client.get("/labels/channel-pool", params={"pool_size": 200})
        items = response.json()["items"]
        match = [item for item in items if item["channel_id"] == BATCH_CHANNEL_ID]
        assert match == []
    finally:
        _cleanup_batch()


def test_post_labels_batch_creates_one_label_per_video_with_shared_labeler_and_label():
    _cleanup_batch()
    try:
        video_ids = _seed_batch_channel(3)

        response = client.post(
            "/labels/batch",
            json={
                "channel_id": BATCH_CHANNEL_ID,
                "video_ids": video_ids,
                "labeler": "alice",
                "label": "down",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body == {
            "channel_id": BATCH_CHANNEL_ID,
            "labeler": "alice",
            "label": "down",
            "video_count": 3,
            "created_at": body["created_at"],
        }

        with session_scope() as session:
            rows = session.query(Label).filter(Label.video_id.in_(video_ids)).all()
            assert len(rows) == 3
            assert all(row.labeler == "alice" and row.label == "down" for row in rows)
    finally:
        _cleanup_batch()


def test_post_labels_batch_404s_and_writes_nothing_if_a_video_id_is_wrong():
    _cleanup_batch()
    try:
        video_ids = _seed_batch_channel(2)

        response = client.post(
            "/labels/batch",
            json={
                "channel_id": BATCH_CHANNEL_ID,
                "video_ids": [*video_ids, "does-not-exist"],
                "labeler": "alice",
                "label": "up",
            },
        )
        assert response.status_code == 404

        with session_scope() as session:
            count = session.query(Label).filter(Label.video_id.in_(video_ids)).count()
        assert count == 0
    finally:
        _cleanup_batch()


def test_post_labels_batch_400s_for_empty_video_ids():
    response = client.post(
        "/labels/batch",
        json={"channel_id": BATCH_CHANNEL_ID, "video_ids": [], "labeler": "alice", "label": "up"},
    )
    assert response.status_code == 400
