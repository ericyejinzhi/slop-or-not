"""Pydantic request/response schemas for the API. Schemas that map directly onto a
single ORM model's scalar columns use from_attributes=True + model_validate(); schemas
blending multiple tables (list/detail items) are built field-by-field in router code
instead, since no single ORM object represents them.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NlpFeatureBreakdown(BaseModel):
    """Scalar (non-vector) columns of VideoNlpFeatures - the 3 embedding columns are
    excluded, not meaningfully serializable in a UI response."""

    model_config = ConfigDict(from_attributes=True)

    comment_count_scored: int
    sentiment_mean: float | None
    sentiment_std: float | None
    sentiment_negative_share: float | None
    slop_keyword_rate: float | None
    topic_cluster_count: int | None
    topic_top_cluster_share: float | None
    topic_top_cluster_sentiment: float | None
    topic_sentiment_spread: float | None
    title_lure_score: float | None
    title_mysterious_score: float | None
    title_transparent_score: float | None


class VisionFeatureBreakdown(BaseModel):
    """Scalar columns of VideoVisionFeatures - excludes image_embedding."""

    model_config = ConfigDict(from_attributes=True)

    clip_clickbait_score: float | None
    clip_ai_generated_score: float | None
    clip_text_heavy_score: float | None


class SimilarVideo(BaseModel):
    video_id: str
    distance: float
    title: str | None
    thumbnail_url: str | None


class VideoListItem(BaseModel):
    id: str
    title: str
    channel_id: str
    channel_handle: str | None
    published_at: datetime
    view_count: int | None
    thumbnail_url: str | None
    score: float | None
    predicted_label: str | None


class VideoListResponse(BaseModel):
    items: list[VideoListItem]
    total: int
    limit: int
    offset: int


class VideoDetail(BaseModel):
    id: str
    title: str
    description: str | None
    channel_id: str
    channel_handle: str | None
    published_at: datetime
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    tags: list[str]
    thumbnail_url: str | None
    score: float | None
    predicted_label: str | None
    model_name: str | None
    model_version: str | None
    nlp_features: NlpFeatureBreakdown | None
    vision_features: VisionFeatureBreakdown | None
    similar_videos: list[SimilarVideo]


class ChannelDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    handle: str | None
    title: str
    description: str | None
    subscriber_count: int | None
    video_count: int | None
    view_count: int | None
    last_ingested_at: datetime | None


class LabelPoolItem(BaseModel):
    video_id: str
    title: str
    channel_id: str
    channel_handle: str | None
    published_at: datetime
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    thumbnail_url: str | None


class LabelPoolResponse(BaseModel):
    items: list[LabelPoolItem]


class ChannelBatchPoolItem(BaseModel):
    channel_id: str
    channel_handle: str | None
    videos: list[LabelPoolItem]


class ChannelBatchPoolResponse(BaseModel):
    items: list[ChannelBatchPoolItem]


class IngestRequest(BaseModel):
    channel: str | None = None
    video_id: str | None = None
    # Channel ingests are always capped. Unset = the project's default random sample (see
    # ingest.pipeline.DEFAULT_SAMPLE_*); set = the N most-recent uploads instead.
    max_videos: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "IngestRequest":
        if (self.channel is None) == (self.video_id is None):
            raise ValueError("Provide exactly one of 'channel' or 'video_id'")
        if self.max_videos is not None and self.channel is None:
            raise ValueError("'max_videos' only applies to a 'channel' ingest")
        return self


class IngestResponse(BaseModel):
    status: Literal["accepted"]
    target: str


class LabelCreateRequest(BaseModel):
    video_id: str
    labeler: str | None = None
    label: Literal["up", "down", "skip"]
    notes: str | None = None


class LabelResponse(BaseModel):
    video_id: str
    labeler: str
    label: str
    notes: str | None
    created_at: datetime


class BatchLabelCreateRequest(BaseModel):
    channel_id: str
    video_ids: list[str]
    labeler: str | None = None
    label: Literal["up", "down", "skip"]
    notes: str | None = None


class BatchLabelResponse(BaseModel):
    channel_id: str
    labeler: str
    label: str
    video_count: int
    created_at: datetime


class LabeledVideoItem(BaseModel):
    """A video's MOST RECENT label (a video may be relabeled - `labels` keeps every row,
    this always reflects the latest judgment). `label_count` is how many times it's been
    labeled in total, surfaced so a relabel isn't made blind to prior history."""

    video_id: str
    title: str
    channel_id: str
    channel_handle: str | None
    thumbnail_url: str | None
    label: str
    labeler: str
    labeled_at: datetime
    label_count: int


class LabeledVideoListResponse(BaseModel):
    items: list[LabeledVideoItem]
    total: int
    limit: int
    offset: int
