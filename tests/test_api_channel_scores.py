"""Channel-level scores (GET /channels and GET /channels/{id}) against the real dev Postgres.

A channel's score is the MEAN of its videos' scores under a model. Each test passes an
explicit, unique model name/version so only the channels created here have scores under it,
independent of whatever model is active in .env."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from sloppy.api.app import app
from sloppy.api.routers import channels as channels_module
from sloppy.config import Settings
from sloppy.db.models import Channel, Video, VideoScore
from sloppy.db.session import session_scope
from sloppy.ingest.upsert import upsert_channel, upsert_video
from sloppy.ingest.youtube import ChannelMeta, VideoMeta
from sloppy.models.scores import upsert_video_score

client = TestClient(app)

MODEL = {"model_name": "test_channel_scores_model", "model_version": "v1"}
SLOPPY, FINE, UNSCORED = "UC_test_cs_sloppy", "UC_test_cs_fine", "UC_test_cs_unscored"
# SLOPPY's scores are deliberately asymmetric: mean 0.5 ("down") but median 0.4 ("up"), so
# a test on it tells a mean apart from a median.
VIDEOS = {
    SLOPPY: [("cs_s1", 0.2), ("cs_s2", 0.4), ("cs_s3", 0.9)],
    FINE: [("cs_f1", 0.1), ("cs_f2", 0.3)],
    UNSCORED: [("cs_u1", None)],
}


def _cleanup() -> None:
    video_ids = [vid for videos in VIDEOS.values() for vid, _ in videos]
    with session_scope() as session:
        session.query(VideoScore).filter(VideoScore.video_id.in_(video_ids)).delete()
        session.query(Video).filter(Video.id.in_(video_ids)).delete()
        session.query(Channel).filter(Channel.id.in_(list(VIDEOS))).delete()


@pytest.fixture
def seeded():
    _cleanup()
    with session_scope() as session:
        for channel_id, videos in VIDEOS.items():
            upsert_channel(
                session,
                ChannelMeta(
                    id=channel_id,
                    handle=f"@{channel_id.lower()}",
                    title=f"Title {channel_id}",
                    subscriber_count=100,
                    uploads_playlist_id="UU_x",
                ),
            )
            for video_id, score in videos:
                upsert_video(
                    session,
                    VideoMeta(
                        id=video_id,
                        channel_id=channel_id,
                        title=f"video {video_id}",
                        published_at=datetime.now(UTC),
                    ),
                )
                if score is not None:
                    upsert_video_score(
                        session,
                        video_id=video_id,
                        model_name=MODEL["model_name"],
                        model_version=MODEL["model_version"],
                        score=score,
                        predicted_label="down" if score >= 0.5 else "up",
                        split="live",
                    )
    yield
    _cleanup()


def test_channel_detail_score_is_the_mean_of_its_video_scores(seeded):
    body = client.get(f"/channels/{SLOPPY}", params=MODEL).json()

    assert body["channel_score"] == pytest.approx(0.5)  # mean of .2 .4 .9 (the median is .4)
    assert body["channel_predicted_label"] == "down"  # at the 0.5 threshold, like a video
    assert body["scored_video_count"] == 3
    assert body["ingested_video_count"] == 3


def test_channel_detail_below_threshold_is_up(seeded):
    body = client.get(f"/channels/{FINE}", params=MODEL).json()

    assert body["channel_score"] == pytest.approx(0.2)
    assert body["channel_predicted_label"] == "up"
    assert body["scored_video_count"] == 2


def test_channel_detail_with_no_scored_videos_has_a_null_score(seeded):
    body = client.get(f"/channels/{UNSCORED}", params=MODEL).json()

    assert body["channel_score"] is None
    assert body["channel_predicted_label"] is None
    assert body["scored_video_count"] == 0
    assert body["ingested_video_count"] == 1


def test_channel_detail_without_any_model_has_a_null_score(seeded, monkeypatch):
    monkeypatch.setattr(channels_module, "get_settings", lambda: Settings(_env_file=None))

    body = client.get(f"/channels/{SLOPPY}").json()

    assert body["channel_score"] is None
    assert body["ingested_video_count"] == 3


def test_list_ranks_channels_by_score_with_unscored_last(seeded):
    body = client.get("/channels", params={**MODEL, "limit": 100}).json()
    ids = [item["id"] for item in body["items"]]

    assert ids.index(SLOPPY) < ids.index(FINE) < ids.index(UNSCORED)
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[SLOPPY]["channel_score"] == pytest.approx(0.5)
    assert by_id[SLOPPY]["scored_video_count"] == 3
    assert by_id[UNSCORED]["channel_score"] is None
    # every scored channel precedes every unscored one
    scored_flags = [item["channel_score"] is not None for item in body["items"]]
    assert scored_flags == sorted(scored_flags, reverse=True)


def test_list_ascending_puts_the_lowest_score_first_and_still_unscored_last(seeded):
    ids = [
        item["id"]
        for item in client.get("/channels", params={**MODEL, "order": "asc", "limit": 100}).json()[
            "items"
        ]
    ]

    assert ids.index(FINE) < ids.index(SLOPPY) < ids.index(UNSCORED)


def test_list_filters_by_predicted_label(seeded):
    down = client.get("/channels", params={**MODEL, "predicted_label": "down"}).json()
    up = client.get("/channels", params={**MODEL, "predicted_label": "up"}).json()

    assert [i["id"] for i in down["items"]] == [SLOPPY] and down["total"] == 1
    assert [i["id"] for i in up["items"]] == [FINE] and up["total"] == 1


def test_list_paginates_and_reports_the_unpaginated_total(seeded):
    full = client.get("/channels", params={**MODEL, "predicted_label": "down"}).json()
    page = client.get("/channels", params={**MODEL, "limit": 1, "offset": 0}).json()

    assert full["total"] == 1
    assert len(page["items"]) == 1
    assert page["total"] >= 3  # at least the three seeded channels
    assert page["limit"] == 1 and page["offset"] == 0


def test_list_sorts_by_title(seeded):
    ids = [
        item["id"]
        for item in client.get(
            "/channels", params={**MODEL, "sort": "title", "order": "asc", "limit": 100}
        ).json()["items"]
    ]

    titles = [i for i in ids if i in (SLOPPY, FINE, UNSCORED)]
    assert titles == sorted(titles, key=lambda c: f"Title {c}".lower())


def test_list_with_no_model_returns_null_scores_and_matches_nothing_by_label(seeded, monkeypatch):
    monkeypatch.setattr(channels_module, "get_settings", lambda: Settings(_env_file=None))

    everything = client.get("/channels", params={"limit": 100}).json()
    labeled = client.get("/channels", params={"predicted_label": "down"}).json()

    assert everything["total"] >= 3
    assert all(item["channel_score"] is None for item in everything["items"])
    assert labeled["total"] == 0 and labeled["items"] == []


def test_list_rejects_an_unknown_sort_column(seeded):
    assert client.get("/channels", params={"sort": "nonsense"}).status_code == 422


def test_channel_detail_404_for_a_missing_channel():
    assert client.get("/channels/does-not-exist").status_code == 404
