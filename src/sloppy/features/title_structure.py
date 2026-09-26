"""Structural title cues - pure stdlib, no ML. Deterministic regex/string counts,
same category as features/text.py, always permanently testable without real data.
"""

import re

CURIOSITY_GAP_PHRASES = (
    "what happened",
    "the truth",
    "you'll never guess",
    "here's why",
    "the reason will",
    "what happens next",
    "wait for it",
)
UNRESOLVED_PRONOUNS = ("this", "that", "these", "those", "her", "his", "their", "its", "it")

_ALL_CAPS_SPAN_RE = re.compile(r"\b[A-Z]{2,}\b")
_ELLIPSIS_RE = re.compile(r"\.\.\.|…")


def curiosity_gap_phrase_count(title: str) -> int:
    lowered = title.lower()
    return sum(1 for phrase in CURIOSITY_GAP_PHRASES if phrase in lowered)


def unresolved_pronoun_count(title: str) -> int:
    words = re.findall(r"[a-zA-Z']+", title.lower())
    pronoun_set = set(UNRESOLVED_PRONOUNS)
    return sum(1 for word in words if word in pronoun_set)


def all_caps_span_count(title: str) -> int:
    return len(_ALL_CAPS_SPAN_RE.findall(title))


def ellipsis_count(title: str) -> int:
    return len(_ELLIPSIS_RE.findall(title))
