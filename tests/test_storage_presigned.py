"""Integration test against the real dev MinIO (docker compose up -d). Proves a
presigned URL is genuinely usable by an unauthenticated HTTP client - the way a browser
<img> tag would use it - not just that generate_presigned_url was called with the right
params (a fake-client test wouldn't prove the URL actually works against real MinIO).
"""

import httpx

from sloppy.config import get_settings
from sloppy.storage import ensure_bucket, generate_presigned_url, get_s3_client

TEST_S3_KEY = "test-storage-presigned/fixture.txt"
TEST_S3_BODY = b"presigned url fixture bytes"


def _cleanup(client, bucket: str) -> None:
    client.delete_object(Bucket=bucket, Key=TEST_S3_KEY)


def test_generate_presigned_url_is_fetchable_without_credentials():
    settings = get_settings()
    client = get_s3_client(settings)
    bucket = settings.s3_bucket_thumbnails
    ensure_bucket(client, bucket)

    try:
        client.put_object(Bucket=bucket, Key=TEST_S3_KEY, Body=TEST_S3_BODY)

        url = generate_presigned_url(client, bucket, TEST_S3_KEY, expires_in=60)

        response = httpx.get(url)
        assert response.status_code == 200
        assert response.content == TEST_S3_BODY
    finally:
        _cleanup(client, bucket)
