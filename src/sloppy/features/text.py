"""Title/description text features. Pure stdlib - no ML dependency, deterministic, and
never needs real data to test since these are hand-computed string transformations."""

import re

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"  # misc symbols/pictographs, emoticons, transport, supplemental
    "☀-⛿"  # misc symbols (☀-⛿)
    "✀-➿"  # dingbats (✀-➿)
    "]"
)

# Deliberately simple, hand-curated lexicon for a metadata-only baseline - not learned.
# Revisit once real labels exist and error analysis (Stage 9) shows what's actually
# predictive; premature to make this fancier before then.
CLICKBAIT_PHRASES = (
    "you won't believe",
    "shocking",
    "gone wrong",
    "gone sexual",
    "insane",
    "must watch",
    "this is why",
    "the truth about",
    "before it's too late",
    "top 10",
    "won't believe what happened",
    "!!!",
    "??",
)


def caps_ratio(title: str) -> float:
    alpha_chars = [c for c in title if c.isalpha()]
    if not alpha_chars:
        return 0.0
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    return upper_count / len(alpha_chars)


def emoji_count(title: str) -> int:
    return len(_EMOJI_RE.findall(title))


def clickbait_score(title: str) -> float:
    lowered = title.lower()
    matches = sum(1 for phrase in CLICKBAIT_PHRASES if phrase in lowered)
    word_count = max(len(title.split()), 1)
    return matches / word_count


def description_length(description: str | None) -> int:
    return len(description or "")


def tag_count(tags: list[str] | None) -> int:
    return len(tags or [])
