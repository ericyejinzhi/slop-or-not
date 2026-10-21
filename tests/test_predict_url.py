"""Link parsing: whatever a visitor pastes must become a video id, or a clear refusal."""

import pytest

from sloppy.predict.errors import InvalidVideoLink
from sloppy.predict.url import parse_video_id

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "pasted",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}&t=42s",
        f"https://www.youtube.com/watch?feature=share&v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=abc123",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}?feature=share",
        f"www.youtube.com/watch?v={VIDEO_ID}",
        f"youtube.com/watch?v={VIDEO_ID}",
        f"  https://youtu.be/{VIDEO_ID}  ",
        VIDEO_ID,
    ],
)
def test_every_common_form_of_a_video_link_yields_the_id(pasted):
    assert parse_video_id(pasted) == VIDEO_ID


@pytest.mark.parametrize(
    "pasted",
    [
        "",
        "   ",
        "hello",
        "https://www.youtube.com/@somechannel",
        "https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx",
        "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=tooshort",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ_toolong",
        "ftp://youtu.be/dQw4w9WgXcQ",
    ],
)
def test_anything_that_names_no_single_video_is_refused(pasted):
    with pytest.raises(InvalidVideoLink):
        parse_video_id(pasted)


def test_a_link_to_another_site_is_not_trusted_even_if_it_looks_like_a_watch_url():
    with pytest.raises(InvalidVideoLink):
        parse_video_id("https://notyoutube.com/watch?v=dQw4w9WgXcQ")
