from unittest.mock import patch

from sloppy.label import display


class _FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self, data: bytes):
        self._data = data
        self.get_calls: list[dict] = []

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)
        return {"Body": _FakeBody(self._data)}


def test_cache_thumbnail_uses_extension_from_content_type(tmp_path, monkeypatch):
    monkeypatch.setattr(display, "_CACHE_DIR", tmp_path)
    client = _FakeS3Client(b"fake-webp-bytes")

    path = display.cache_thumbnail(client, "video123", "thumbnails", "video123.jpg", "image/webp")

    assert path.suffix == ".webp"
    assert path.read_bytes() == b"fake-webp-bytes"
    assert client.get_calls == [{"Bucket": "thumbnails", "Key": "video123.jpg"}]


def test_cache_thumbnail_reuses_existing_cache_file(tmp_path, monkeypatch):
    monkeypatch.setattr(display, "_CACHE_DIR", tmp_path)
    client = _FakeS3Client(b"first-download")

    path1 = display.cache_thumbnail(client, "video123", "thumbnails", "video123.jpg", "image/jpeg")
    client._data = b"second-download"  # should not be re-fetched
    path2 = display.cache_thumbnail(client, "video123", "thumbnails", "video123.jpg", "image/jpeg")

    assert path1 == path2
    assert path1.read_bytes() == b"first-download"
    assert len(client.get_calls) == 1


def test_extension_for_content_type_does_not_silently_fall_back_to_jpg_for_webp():
    # Regression test: stdlib mimetypes.guess_extension("image/webp") returns None on
    # some systems (confirmed on this one), which would silently mislabel WebP bytes as
    # .jpg if we relied on it alone.
    assert display._extension_for_content_type("image/webp") == ".webp"
    assert display._extension_for_content_type("image/jpeg") == ".jpg"


def test_open_image_calls_os_startfile(tmp_path):
    target = tmp_path / "preview.jpg"
    target.write_bytes(b"x")
    with patch("os.startfile") as mock_startfile:
        display.open_image(target)
    mock_startfile.assert_called_once_with(target)
