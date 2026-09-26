from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from sloppy.db.base import Base, TimestampMixin


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    handle: Mapped[str | None] = mapped_column(Text, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    subscriber_count: Mapped[int | None] = mapped_column(BigInteger)
    video_count: Mapped[int | None] = mapped_column(BigInteger)
    view_count: Mapped[int | None] = mapped_column(BigInteger)
    uploads_playlist_id: Mapped[str] = mapped_column(Text)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    channel_id: Mapped[str] = mapped_column(Text, ForeignKey("channels.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger)
    view_count: Mapped[int | None] = mapped_column(BigInteger)
    like_count: Mapped[int | None] = mapped_column(BigInteger)
    comment_count: Mapped[int | None] = mapped_column(BigInteger)
    topic_categories: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    thumbnail_url: Mapped[str | None] = mapped_column(Text)


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    video_id: Mapped[str] = mapped_column(Text, ForeignKey("videos.id"), index=True)
    author_display_name: Mapped[str | None] = mapped_column(Text)
    author_channel_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int | None] = mapped_column(BigInteger)
    reply_count: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Thumbnail(Base, TimestampMixin):
    __tablename__ = "thumbnails"

    video_id: Mapped[str] = mapped_column(Text, ForeignKey("videos.id"), primary_key=True)
    s3_bucket: Mapped[str] = mapped_column(Text)
    s3_key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(BigInteger)
    height: Mapped[int | None] = mapped_column(BigInteger)
    source_url: Mapped[str] = mapped_column(Text)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Label(Base, TimestampMixin):
    """A single labeling judgment. video_id is intentionally NOT unique - relabeling the
    same video (e.g. a consistency spot-check) is expected to add a new row, not overwrite
    the old one. `created_at` (from TimestampMixin) is that judgment's timestamp.
    """

    __tablename__ = "labels"
    __table_args__ = (
        CheckConstraint("label IN ('up', 'down', 'skip')", name="ck_labels_label_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(Text, ForeignKey("videos.id"), index=True)
    labeler: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
