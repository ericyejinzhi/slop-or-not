"""Shared helper for routers that need to turn a Thumbnail row into a presigned URL."""

from sloppy.db.models import Thumbnail
from sloppy.storage import generate_presigned_url


def presigned_thumbnail_url(s3_client, thumbnail: Thumbnail | None) -> str | None:
    if thumbnail is None:
        return None
    return generate_presigned_url(s3_client, thumbnail.s3_bucket, thumbnail.s3_key)
