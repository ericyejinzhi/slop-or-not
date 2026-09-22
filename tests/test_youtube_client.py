from sloppy.ingest.youtube import _best_thumbnail_url, parse_duration


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
