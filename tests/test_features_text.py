from sloppy.features.text import (
    caps_ratio,
    clickbait_score,
    description_length,
    emoji_count,
    tag_count,
)


def test_caps_ratio_all_caps():
    assert caps_ratio("HELLO WORLD") == 1.0


def test_caps_ratio_no_caps():
    assert caps_ratio("hello world") == 0.0


def test_caps_ratio_mixed():
    # "Hi" -> 1 upper / 2 alpha = 0.5
    assert caps_ratio("Hi") == 0.5


def test_caps_ratio_no_alpha_chars_returns_zero():
    assert caps_ratio("123 !!! ???") == 0.0


def test_emoji_count_counts_emoji_only():
    assert emoji_count("great video 😱😱 check it out") == 2
    assert emoji_count("no emoji here") == 0


def test_clickbait_score_matches_known_phrases():
    title = "YOU WON'T BELIEVE THIS!!! SHOCKING TRUTH"
    # matches: "you won't believe" (also matches "won't believe what happened"? no, that
    # phrase requires "what happened" too, so only "you won't believe" and "!!!" match
    # from CLICKBAIT_PHRASES here) plus "shocking" -> 3 matches / 5 words
    score = clickbait_score(title)
    assert score > 0


def test_clickbait_score_zero_for_plain_title():
    assert clickbait_score("How to replace a bike chain") == 0.0


def test_description_length_handles_none():
    assert description_length(None) == 0
    assert description_length("hello") == 5


def test_tag_count_handles_none():
    assert tag_count(None) == 0
    assert tag_count(["a", "b", "c"]) == 3
