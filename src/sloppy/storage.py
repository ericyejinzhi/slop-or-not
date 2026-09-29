"""Object storage client (MinIO locally, S3 later — identical boto3 API)."""

import boto3
from botocore.client import Config

from sloppy.config import Settings


def get_s3_client(settings: Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket(client, bucket: str) -> None:
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)


def generate_presigned_url(client, bucket: str, key: str, expires_in: int = 3600) -> str:
    """A time-limited, unauthenticated GET URL for an object - lets a browser <img> tag
    load a thumbnail directly from MinIO/S3 without the API proxying the bytes itself.

    Note: the endpoint baked into the URL is whatever `client` was constructed with
    (settings.s3_endpoint_url) at generation time. A client running inside docker-compose
    (resolving MinIO at http://minio:9000) will produce URLs unreachable from a host
    browser - see Phase 5 Stage 4's write-up.
    """
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
    )
