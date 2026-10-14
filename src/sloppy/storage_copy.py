"""Copy objects between S3-compatible buckets (MinIO -> S3, for the first deployment).

The cloud bucket starts empty; the thumbnails live in the local MinIO. `copy_objects`
copies a set of keys and is safe to re-run: an object that already exists at the
destination with the same size is skipped, so an interrupted copy resumes where it
stopped instead of starting over.
"""

import os
from dataclasses import dataclass, field

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


def get_destination_client(endpoint_url: str | None = None, region: str = "us-east-1"):
    """An S3 client for the DESTINATION. Credentials come from DEST_AWS_ACCESS_KEY_ID /
    DEST_AWS_SECRET_ACCESS_KEY if both are set, otherwise from boto3's default chain
    (AWS_* environment variables, a profile, an instance role) - so the destination's
    credentials are never mixed up with the source MinIO's keys in .env. `endpoint_url`
    is for S3-compatible targets (and tests); leave it unset for real AWS S3."""
    kwargs: dict = {"region_name": region, "config": Config(signature_version="s3v4")}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    access_key = os.environ.get("DEST_AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("DEST_AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


@dataclass
class CopyResult:
    copied: int = 0  # in a dry run: how many WOULD be copied
    skipped: int = 0  # already at the destination with the same size
    bytes_copied: int = 0
    missing: list[str] = field(default_factory=list)  # not in the source bucket
    failed: list[str] = field(default_factory=list)  # any other error, with the reason


def _is_not_found(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code")) in _NOT_FOUND_CODES


def copy_objects(
    src_client,
    dst_client,
    dst_bucket: str,
    objects: list[tuple[str, str]],
    dry_run: bool = False,
) -> CopyResult:
    """Copy each (source_bucket, key) in `objects` to the same key in `dst_bucket`.
    One object's failure is recorded and does not stop the rest."""
    result = CopyResult()
    for src_bucket, key in objects:
        try:
            head = src_client.head_object(Bucket=src_bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                result.missing.append(f"{src_bucket}/{key}")
            else:
                result.failed.append(f"{src_bucket}/{key}: {exc}")
            continue

        size = head["ContentLength"]
        try:
            existing = dst_client.head_object(Bucket=dst_bucket, Key=key)
            if existing["ContentLength"] == size:
                result.skipped += 1
                continue
        except ClientError as exc:
            if not _is_not_found(exc):
                result.failed.append(f"{dst_bucket}/{key}: {exc}")
                continue

        if dry_run:
            result.copied += 1
            result.bytes_copied += size
            continue

        try:
            body = src_client.get_object(Bucket=src_bucket, Key=key)["Body"].read()
            dst_client.put_object(
                Bucket=dst_bucket,
                Key=key,
                Body=body,
                ContentType=head.get("ContentType", "application/octet-stream"),
            )
        except ClientError as exc:
            result.failed.append(f"{src_bucket}/{key}: {exc}")
            continue
        result.copied += 1
        result.bytes_copied += size
    return result
