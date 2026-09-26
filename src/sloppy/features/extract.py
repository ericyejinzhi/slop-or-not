"""Combines the text/duration/corpus feature functions into one flat VideoFeatures
record per video."""

from dataclasses import dataclass
from typing import Protocol

from sloppy.features.corpus import CorpusStats, VideoLike, primary_genre, upload_cadence_days
from sloppy.features.duration import duration_bucket, duration_deviation
from sloppy.features.text import (
    caps_ratio,
    clickbait_score,
    description_length,
    emoji_count,
    tag_count,
)
from sloppy.features.title_structure import (
    all_caps_span_count,
    curiosity_gap_phrase_count,
    ellipsis_count,
    unresolved_pronoun_count,
)


class ExtractableVideo(VideoLike, Protocol):
    title: str
    description: str | None
    tags: list[str] | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None


@dataclass
class VideoFeatures:
    video_id: str
    channel_id: str
    title_caps_ratio: float
    title_emoji_count: int
    title_clickbait_score: float
    description_length: int
    tag_count: int
    like_view_ratio: float | None
    comment_view_ratio: float | None
    duration_seconds: int | None
    duration_bucket: str
    duration_deviation_channel: float | None
    duration_deviation_genre: float | None
    channel_upload_cadence_days: float | None
    genre: str
    title_curiosity_gap_count: int
    title_unresolved_pronoun_count: int
    title_all_caps_span_count: int
    title_ellipsis_count: int


def like_view_ratio(like_count: int | None, view_count: int | None) -> float | None:
    if not view_count:
        return None
    return (like_count or 0) / view_count


def comment_view_ratio(comment_count: int | None, view_count: int | None) -> float | None:
    if not view_count:
        return None
    return (comment_count or 0) / view_count


def extract_features(video: ExtractableVideo, corpus: CorpusStats) -> VideoFeatures:
    genre = primary_genre(video.topic_categories)
    channel_peers = corpus.durations_by_channel.get(video.channel_id, [])
    genre_peers = corpus.durations_by_genre.get(genre, [])
    cadence = upload_cadence_days(corpus.published_dates_by_channel.get(video.channel_id, []))

    return VideoFeatures(
        video_id=video.id,
        channel_id=video.channel_id,
        title_caps_ratio=caps_ratio(video.title),
        title_emoji_count=emoji_count(video.title),
        title_clickbait_score=clickbait_score(video.title),
        description_length=description_length(video.description),
        tag_count=tag_count(video.tags),
        like_view_ratio=like_view_ratio(video.like_count, video.view_count),
        comment_view_ratio=comment_view_ratio(video.comment_count, video.view_count),
        duration_seconds=video.duration_seconds,
        duration_bucket=duration_bucket(video.duration_seconds),
        duration_deviation_channel=duration_deviation(video.duration_seconds, channel_peers),
        duration_deviation_genre=duration_deviation(video.duration_seconds, genre_peers),
        channel_upload_cadence_days=cadence,
        genre=genre,
        title_curiosity_gap_count=curiosity_gap_phrase_count(video.title),
        title_unresolved_pronoun_count=unresolved_pronoun_count(video.title),
        title_all_caps_span_count=all_caps_span_count(video.title),
        title_ellipsis_count=ellipsis_count(video.title),
    )
