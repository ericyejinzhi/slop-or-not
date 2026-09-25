import pytest

from sloppy.config import Settings
from sloppy.ingest.thumbnails import _pick_best_thumbnail, upload_thumbnail


def test_pick_best_thumbnail_selects_largest_area():
    thumbnails = [
        {"url": "small.jpg", "width": 120, "height": 90},
        {"url": "large.jpg", "width": 1280, "height": 720},
        {"url": "medium.jpg", "width": 480, "height": 360},
    ]
    assert _pick_best_thumbnail(thumbnails)["url"] == "large.jpg"


def test_pick_best_thumbnail_ignores_entries_without_dimensions():
    thumbnails = [
        {"url": "no-dims.jpg"},
        {"url": "has-dims.jpg", "width": 100, "height": 100},
    ]
    assert _pick_best_thumbnail(thumbnails)["url"] == "has-dims.jpg"


def test_pick_best_thumbnail_raises_when_none_have_dimensions():
    with pytest.raises(ValueError, match="No thumbnail"):
        _pick_best_thumbnail([{"url": "no-dims.jpg"}])


class _FakeS3Client:
    def __init__(self):
        self.put_calls: list[dict] = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)


def test_upload_thumbnail_uses_video_id_key_and_configured_bucket():
    settings = Settings(_env_file=None, s3_bucket_thumbnails="thumbnails")
    client = _FakeS3Client()

    key = upload_thumbnail(client, settings, "video123", b"fake-bytes", "image/jpeg")

    assert key == "video123.jpg"
    assert client.put_calls == [
        {
            "Bucket": "thumbnails",
            "Key": "video123.jpg",
            "Body": b"fake-bytes",
            "ContentType": "image/jpeg",
        }
    ]
