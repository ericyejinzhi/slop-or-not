"""Idempotent upsert helpers for ingest data. Every table's PK is YouTube's own id, so a
re-run is always an ON CONFLICT DO UPDATE, never a delete-and-reinsert.
"""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sloppy.db.models import Channel, Comment, Thumbnail, Video
from sloppy.ingest.youtube import ChannelMeta, CommentMeta, VideoMeta


def upsert_channel(session: Session, channel: ChannelMeta) -> None:
    stmt = insert(Channel).values(
        id=channel.id,
        handle=channel.handle,
        title=channel.title,
        description=channel.description,
        subscriber_count=channel.subscriber_count,
        video_count=channel.video_count,
        view_count=channel.view_count,
        uploads_playlist_id=channel.uploads_playlist_id,
    )
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in (
            "handle",
            "title",
            "description",
            "subscriber_count",
            "video_count",
            "view_count",
            "uploads_playlist_id",
        )
    }
    update_cols["updated_at"] = func.now()
    session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols))


def upsert_video(session: Session, video: VideoMeta) -> None:
    stmt = insert(Video).values(
        id=video.id,
        channel_id=video.channel_id,
        title=video.title,
        description=video.description,
        published_at=video.published_at,
        duration_seconds=video.duration_seconds,
        view_count=video.view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
        topic_categories=video.topic_categories,
        tags=video.tags,
        thumbnail_url=video.thumbnail_url,
    )
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in (
            "title",
            "description",
            "published_at",
            "duration_seconds",
            "view_count",
            "like_count",
            "comment_count",
            "topic_categories",
            "tags",
            "thumbnail_url",
        )
    }
    update_cols["updated_at"] = func.now()
    session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols))


def upsert_comment(session: Session, comment: CommentMeta) -> None:
    stmt = insert(Comment).values(
        id=comment.id,
        video_id=comment.video_id,
        author_display_name=comment.author_display_name,
        author_channel_id=comment.author_channel_id,
        text=comment.text,
        like_count=comment.like_count,
        reply_count=comment.reply_count,
        published_at=comment.published_at,
    )
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in (
            "author_display_name",
            "author_channel_id",
            "text",
            "like_count",
            "reply_count",
            "published_at",
        )
    }
    update_cols["updated_at"] = func.now()
    session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols))


def upsert_thumbnail(
    session: Session,
    *,
    video_id: str,
    s3_bucket: str,
    s3_key: str,
    content_type: str,
    width: int | None,
    height: int | None,
    source_url: str,
    downloaded_at: datetime,
) -> None:
    stmt = insert(Thumbnail).values(
        video_id=video_id,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        content_type=content_type,
        width=width,
        height=height,
        source_url=source_url,
        downloaded_at=downloaded_at,
    )
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in (
            "s3_bucket",
            "s3_key",
            "content_type",
            "width",
            "height",
            "source_url",
            "downloaded_at",
        )
    }
    update_cols["updated_at"] = func.now()
    session.execute(stmt.on_conflict_do_update(index_elements=["video_id"], set_=update_cols))
