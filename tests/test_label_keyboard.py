from sloppy.label.keyboard import action_for_key


def test_action_for_key_maps_expected_keys():
    assert action_for_key("y") == "up"
    assert action_for_key("n") == "down"
    assert action_for_key("s") == "skip"
    assert action_for_key("q") == "quit"


def test_action_for_key_is_case_insensitive():
    assert action_for_key("Y") == "up"
    assert action_for_key("N") == "down"


def test_action_for_key_returns_none_for_unmapped_key():
    assert action_for_key("x") is None
    assert action_for_key("") is None
