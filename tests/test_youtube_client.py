from sloppy.ingest.youtube import _best_thumbnail_url, _parse_comment_thread, parse_duration


def test_parse_duration_hours_minutes_seconds():
    assert parse_duration("PT1H2M3S") == 3723


def test_parse_duration_minutes_only():
    assert parse_duration("PT15M") == 900


def test_parse_duration_seconds_only():
    assert parse_duration("PT45S") == 45


def test_parse_duration_empty_or_invalid_returns_none():
    assert parse_duration("") is None
    assert parse_duration("not-a-duration") is None


def test_best_thumbnail_url_prefers_highest_resolution():
    thumbnails = {
        "default": {"url": "default.jpg"},
        "high": {"url": "high.jpg"},
        "maxres": {"url": "maxres.jpg"},
    }
    assert _best_thumbnail_url(thumbnails) == "maxres.jpg"


def test_best_thumbnail_url_falls_back_when_missing_higher_res():
    thumbnails = {"default": {"url": "default.jpg"}}
    assert _best_thumbnail_url(thumbnails) == "default.jpg"


def test_best_thumbnail_url_empty_returns_none():
    assert _best_thumbnail_url({}) is None


def _comment_thread_item(**overrides) -> dict:
    snippet = {
        "authorDisplayName": "Some Viewer",
        "authorChannelId": {"value": "UCviewerchannel"},
        "textOriginal": "great video",
        "likeCount": 12,
        "publishedAt": "2026-01-01T00:00:00Z",
    }
    snippet.update(overrides)
    return {
        "snippet": {
            "totalReplyCount": 3,
            "topLevelComment": {"id": "comment123", "snippet": snippet},
        }
    }


def test_parse_comment_thread_extracts_fields():
    comment = _parse_comment_thread(_comment_thread_item(), video_id="video123")
    assert comment.id == "comment123"
    assert comment.video_id == "video123"
    assert comment.author_display_name == "Some Viewer"
    assert comment.author_channel_id == "UCviewerchannel"
    assert comment.text == "great video"
    assert comment.like_count == 12
    assert comment.reply_count == 3


def test_parse_comment_thread_handles_missing_author_channel_id():
    comment = _parse_comment_thread(_comment_thread_item(authorChannelId=None), video_id="video123")
    assert comment.author_channel_id is None
