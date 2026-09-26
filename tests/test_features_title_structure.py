from sloppy.features.title_structure import (
    all_caps_span_count,
    curiosity_gap_phrase_count,
    ellipsis_count,
    unresolved_pronoun_count,
)


def test_curiosity_gap_phrase_count_matches_known_phrases():
    assert curiosity_gap_phrase_count("Here's why this happened") == 1
    assert curiosity_gap_phrase_count("What happened next will shock you") == 1
    assert curiosity_gap_phrase_count("What happens next in the story") == 1
    assert curiosity_gap_phrase_count("How to replace a bike chain") == 0


def test_unresolved_pronoun_count_counts_whole_words_only():
    assert unresolved_pronoun_count("This is her secret") == 2  # "this", "her"
    assert unresolved_pronoun_count("How to replace a bike chain") == 0
    # "history" contains "his" as a substring but is not the whole word "his"
    assert unresolved_pronoun_count("A brief history of Rome") == 0


def test_all_caps_span_count_ignores_single_letters_and_lowercase():
    assert all_caps_span_count("This is INSANE and CRAZY") == 2
    assert all_caps_span_count("A cat sat on a mat") == 0
    assert all_caps_span_count("I am here") == 0  # single-letter "I" doesn't count


def test_ellipsis_count_matches_both_ascii_and_unicode_ellipsis():
    assert ellipsis_count("wait for it...") == 1
    assert ellipsis_count("wait for it…") == 1
    assert ellipsis_count("no ellipsis here") == 0
    assert ellipsis_count("one... then another...") == 2
