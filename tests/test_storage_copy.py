"""copy_objects against the real local MinIO, using two throwaway buckets."""

import uuid

import pytest
from botocore.exceptions import ClientError

from sloppy.config import Settings
from sloppy.storage import ensure_bucket, get_s3_client
from sloppy.storage_copy import copy_objects

SETTINGS = Settings(_env_file=None)  # defaults point at the local MinIO


@pytest.fixture
def buckets():
    client = get_s3_client(SETTINGS)
    src, dst = (f"test-copy-{tag}-{uuid.uuid4().hex[:10]}" for tag in ("src", "dst"))
    ensure_bucket(client, src)
    ensure_bucket(client, dst)
    yield client, src, dst
    for bucket in (src, dst):
        try:
            for obj in client.list_objects_v2(Bucket=bucket).get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
            client.delete_bucket(Bucket=bucket)
        except ClientError:
            pass


def _put(client, bucket, key, body=b"x", content_type="image/jpeg"):
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


def test_copies_objects_with_their_bytes_and_content_type(buckets):
    client, src, dst = buckets
    _put(client, src, "a.jpg", b"alpha-bytes" * 100)
    _put(client, src, "b.jpg", b"beta", content_type="image/png")

    result = copy_objects(client, client, dst, [(src, "a.jpg"), (src, "b.jpg")])

    assert (result.copied, result.skipped, result.missing, result.failed) == (2, 0, [], [])
    assert result.bytes_copied == len(b"alpha-bytes" * 100) + len(b"beta")
    got = client.get_object(Bucket=dst, Key="a.jpg")
    assert got["Body"].read() == b"alpha-bytes" * 100
    assert client.head_object(Bucket=dst, Key="b.jpg")["ContentType"] == "image/png"


def test_rerunning_skips_what_is_already_there(buckets):
    client, src, dst = buckets
    _put(client, src, "a.jpg", b"1234")
    objects = [(src, "a.jpg")]

    first = copy_objects(client, client, dst, objects)
    second = copy_objects(client, client, dst, objects)

    assert (first.copied, first.skipped) == (1, 0)
    assert (second.copied, second.skipped, second.bytes_copied) == (0, 1, 0)


def test_an_object_whose_size_differs_at_the_destination_is_recopied(buckets):
    client, src, dst = buckets
    _put(client, src, "a.jpg", b"the-new-longer-version")
    _put(client, dst, "a.jpg", b"old")

    result = copy_objects(client, client, dst, [(src, "a.jpg")])

    assert result.copied == 1
    assert client.get_object(Bucket=dst, Key="a.jpg")["Body"].read() == b"the-new-longer-version"


def test_a_dry_run_reports_what_would_be_copied_and_writes_nothing(buckets):
    client, src, dst = buckets
    _put(client, src, "a.jpg", b"abcd")

    result = copy_objects(client, client, dst, [(src, "a.jpg")], dry_run=True)

    assert (result.copied, result.bytes_copied) == (1, 4)
    assert client.list_objects_v2(Bucket=dst).get("Contents") is None


def test_a_missing_source_object_is_reported_and_the_rest_still_copy(buckets):
    client, src, dst = buckets
    _put(client, src, "real.jpg", b"ok")

    result = copy_objects(client, client, dst, [(src, "ghost.jpg"), (src, "real.jpg")])

    assert result.missing == [f"{src}/ghost.jpg"]
    assert result.copied == 1
    assert client.get_object(Bucket=dst, Key="real.jpg")["Body"].read() == b"ok"


def test_an_unwritable_destination_is_reported_as_failed_not_raised(buckets):
    client, src, _dst = buckets
    _put(client, src, "a.jpg", b"ok")

    result = copy_objects(
        client, client, "no-such-bucket-" + uuid.uuid4().hex[:8], [(src, "a.jpg")]
    )

    assert result.copied == 0
    assert len(result.failed) == 1
