from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
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


class VideoScore(Base, TimestampMixin):
    """A model's prediction for a video. Keyed on (video_id, model_name, model_version) -
    unlike Label, this is upserted, not append-only: a score is a reproducible function of
    a specific model version scoring a specific video, so re-scoring with the SAME model
    version overwrites, while different model names/versions coexist for comparison.
    """

    __tablename__ = "video_scores"
    __table_args__ = (
        CheckConstraint("predicted_label IN ('up', 'down')", name="ck_video_scores_label_value"),
        Index("ix_video_scores_model_name_version", "model_name", "model_version"),
    )

    video_id: Mapped[str] = mapped_column(Text, ForeignKey("videos.id"), primary_key=True)
    model_name: Mapped[str] = mapped_column(Text, primary_key=True)
    model_version: Mapped[str] = mapped_column(Text, primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    predicted_label: Mapped[str] = mapped_column(Text)
    split: Mapped[str] = mapped_column(Text)


class VideoNlpFeatures(Base, TimestampMixin):
    """NLP feature aggregates + embeddings for one video. Keyed on video_id alone and
    upserted (like VideoScore's reasoning, unlike Label's) - these are reproducible
    function outputs of a specific model checkpoint, not human judgments. Checkpoint
    names are plain provenance columns, not part of the key: there's no product need to
    compare sentiment/embeddings across checkpoint versions side by side the way
    VideoScore compares model predictions, so re-running with a new checkpoint just
    overwrites.
    """

    __tablename__ = "video_nlp_features"

    video_id: Mapped[str] = mapped_column(Text, ForeignKey("videos.id"), primary_key=True)
    comment_count_scored: Mapped[int] = mapped_column(Integer)
    sentiment_mean: Mapped[float | None] = mapped_column(Float)
    sentiment_std: Mapped[float | None] = mapped_column(Float)
    sentiment_negative_share: Mapped[float | None] = mapped_column(Float)
    slop_keyword_rate: Mapped[float | None] = mapped_column(Float)
    topic_cluster_count: Mapped[int | None] = mapped_column(Integer)
    topic_top_cluster_share: Mapped[float | None] = mapped_column(Float)
    topic_top_cluster_sentiment: Mapped[float | None] = mapped_column(Float)
    topic_sentiment_spread: Mapped[float | None] = mapped_column(Float)
    title_lure_score: Mapped[float | None] = mapped_column(Float)
    title_mysterious_score: Mapped[float | None] = mapped_column(Float)
    title_transparent_score: Mapped[float | None] = mapped_column(Float)
    title_embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    description_embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    comment_embedding_mean: Mapped[list[float] | None] = mapped_column(Vector(384))
    sentiment_model: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(Text)


class VideoVisionFeatures(Base, TimestampMixin):
    """CLIP thumbnail embedding + zero-shot scores for one video. Same keying rationale
    as VideoNlpFeatures - upserted on video_id alone, checkpoint name as a plain
    provenance column. FK to videos.id (not thumbnails.video_id) decouples vision-feature
    recompute from any particular thumbnail row's lifecycle.
    """

    __tablename__ = "video_vision_features"

    video_id: Mapped[str] = mapped_column(Text, ForeignKey("videos.id"), primary_key=True)
    image_embedding: Mapped[list[float] | None] = mapped_column(Vector(512))
    clip_clickbait_score: Mapped[float | None] = mapped_column(Float)
    clip_ai_generated_score: Mapped[float | None] = mapped_column(Float)
    clip_text_heavy_score: Mapped[float | None] = mapped_column(Float)
    clip_model: Mapped[str] = mapped_column(Text)
