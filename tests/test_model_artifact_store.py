"""Publishing and fetching trained-model artifacts. The happy path runs against the real
local MinIO (same approach as tests/test_storage.py) in a throwaway bucket; failure
handling uses a stub client so it is deterministic."""

import uuid

import pytest
from botocore.exceptions import ClientError

from sloppy.config import Settings
from sloppy.models import artifact_store
from sloppy.models.artifact_store import (
    download_model,
    ensure_local_model,
    is_local,
    upload_model,
)
from sloppy.storage import get_s3_client

NAME = "logistic_regression"
VERSION = "20260101-000000"
SETTINGS = Settings(_env_file=None)  # defaults point at the local MinIO


def _make_local_model(artifacts_dir, payload=b"fake-joblib-bytes", metadata=b'{"features": []}'):
    model_dir = artifacts_dir / NAME / VERSION
    model_dir.mkdir(parents=True)
    (model_dir / "model.joblib").write_bytes(payload)
    (model_dir / "metadata.json").write_bytes(metadata)


@pytest.fixture
def bucket():
    client = get_s3_client(SETTINGS)
    name = f"test-models-{uuid.uuid4().hex[:12]}"
    yield name
    try:
        for obj in client.list_objects_v2(Bucket=name).get("Contents", []):
            client.delete_object(Bucket=name, Key=obj["Key"])
        client.delete_bucket(Bucket=name)
    except ClientError:
        pass  # the test never created it


def test_upload_then_download_round_trips_the_exact_bytes(tmp_path, bucket):
    source, target = tmp_path / "trained", tmp_path / "server"
    _make_local_model(source, payload=b"\x00\x01binary\xff" * 1000)
    client = get_s3_client(SETTINGS)

    keys = upload_model(client, bucket, source, NAME, VERSION)
    model_dir = download_model(client, bucket, target, NAME, VERSION)

    assert keys == [f"{NAME}/{VERSION}/model.joblib", f"{NAME}/{VERSION}/metadata.json"]
    assert (model_dir / "model.joblib").read_bytes() == b"\x00\x01binary\xff" * 1000
    assert (model_dir / "metadata.json").read_bytes() == b'{"features": []}'
    assert is_local(target, NAME, VERSION)
    assert not list(model_dir.glob("*.part"))


def test_upload_refuses_a_model_that_is_not_fully_on_disk(tmp_path, bucket):
    model_dir = tmp_path / NAME / VERSION
    model_dir.mkdir(parents=True)
    (model_dir / "model.joblib").write_bytes(b"x")  # metadata.json missing

    with pytest.raises(FileNotFoundError, match="metadata.json"):
        upload_model(get_s3_client(SETTINGS), bucket, tmp_path, NAME, VERSION)


def test_ensure_local_model_downloads_only_when_enabled_and_missing(tmp_path, bucket):
    source, target = tmp_path / "trained", tmp_path / "server"
    _make_local_model(source)
    upload_model(get_s3_client(SETTINGS), bucket, source, NAME, VERSION)
    enabled = Settings(_env_file=None, fetch_model_from_s3=True, s3_bucket_models=bucket)
    disabled = Settings(_env_file=None, fetch_model_from_s3=False, s3_bucket_models=bucket)

    assert ensure_local_model(disabled, target, NAME, VERSION) is False  # flag off
    assert not is_local(target, NAME, VERSION)

    assert ensure_local_model(enabled, target, NAME, VERSION) is True  # downloaded
    assert is_local(target, NAME, VERSION)

    assert ensure_local_model(enabled, target, NAME, VERSION) is False  # already local


def test_ensure_local_model_does_not_touch_storage_when_the_model_is_already_local(
    tmp_path, monkeypatch
):
    _make_local_model(tmp_path)
    monkeypatch.setattr(
        artifact_store, "get_s3_client", lambda settings: pytest.fail("must not connect")
    )
    enabled = Settings(_env_file=None, fetch_model_from_s3=True)

    assert ensure_local_model(enabled, tmp_path, NAME, VERSION) is False


def test_ensure_local_model_swallows_a_missing_remote_model(tmp_path, bucket, caplog):
    # nothing was ever published to this bucket, so the download fails
    enabled = Settings(_env_file=None, fetch_model_from_s3=True, s3_bucket_models=bucket)

    assert ensure_local_model(enabled, tmp_path, NAME, VERSION) is False

    assert "Could not fetch model" in caplog.text
    assert not is_local(tmp_path, NAME, VERSION)


class _FailsOnSecondFile:
    """Writes the first requested file, then raises - as a dropped connection would."""

    def __init__(self):
        self.calls = 0

    def download_file(self, bucket, key, filename):
        self.calls += 1
        if self.calls == 2:
            raise ClientError({"Error": {"Code": "500", "Message": "boom"}}, "GetObject")
        with open(filename, "wb") as f:
            f.write(b"partial")


def test_a_failed_download_leaves_no_half_written_model_behind(tmp_path):
    with pytest.raises(ClientError):
        download_model(_FailsOnSecondFile(), "b", tmp_path, NAME, VERSION)

    model_dir = tmp_path / NAME / VERSION
    assert not is_local(tmp_path, NAME, VERSION)
    assert not (model_dir / "model.joblib").exists()  # never renamed into place
    assert not list(model_dir.glob("*.part"))  # and the partials were cleaned up
