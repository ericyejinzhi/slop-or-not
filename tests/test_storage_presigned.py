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


def _offline_settings(**overrides):
    from sloppy.config import Settings

    values = {
        "_env_file": None,
        "s3_endpoint_url": None,
        "s3_access_key": "AKIAEXAMPLE",
        "s3_secret_key": "secret",
        "aws_region": "us-east-2",
    }
    values.update(overrides)
    return Settings(**values)


def test_presigned_urls_for_real_s3_name_the_buckets_region_in_the_host():
    # Regression: with only a region set, boto3 signed for us-east-2 but pointed the URL at
    # the global host, and S3 answered 400 AuthorizationQueryParametersError on a real
    # deployment. The region must appear in the host.
    client = get_s3_client(_offline_settings())

    url = generate_presigned_url(client, "my-bucket", "k.jpg")

    assert url.startswith("https://my-bucket.s3.us-east-2.amazonaws.com/k.jpg?")
    assert "X-Amz-Credential=AKIAEXAMPLE%2F" in url
    assert "us-east-2%2Fs3%2Faws4_request" in url


def test_presigned_urls_for_real_s3_in_us_east_1_still_work():
    client = get_s3_client(_offline_settings(aws_region="us-east-1"))

    url = generate_presigned_url(client, "my-bucket", "k.jpg")

    assert url.startswith("https://my-bucket.s3.")
    assert "amazonaws.com/k.jpg?" in url


def test_a_custom_endpoint_such_as_minio_keeps_path_style_urls():
    client = get_s3_client(_offline_settings(s3_endpoint_url="http://localhost:9000"))

    url = generate_presigned_url(client, "my-bucket", "k.jpg")

    # bucket in the path, not as a subdomain of the endpoint (which would not resolve)
    assert url.startswith("http://localhost:9000/my-bucket/k.jpg?")
