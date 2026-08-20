"""Name normalization — the classic multi-source failure point.

"A.J. Brown" / "AJ Brown", "James Cook III" / "James Cook", "D/ST" naming —
all sources must land on the same key before any name-based join.
"""

import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PUNCT = re.compile(r"[.'’]")  # noqa: RUF001 — curly apostrophe appears in real feeds
_NON_WORD = re.compile(r"[^a-z0-9 ]")
_SPACES = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    # Fold accents to ASCII: sources disagree on diacritics (FFC "Piñeiro",
    # Sleeper "Pineiro"), and _NON_WORD would otherwise split the name there.
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    s = _PUNCT.sub("", name.lower())
    s = _NON_WORD.sub(" ", s)
    parts = [p for p in _SPACES.split(s.strip()) if p and p not in _SUFFIXES]
    return " ".join(parts)
