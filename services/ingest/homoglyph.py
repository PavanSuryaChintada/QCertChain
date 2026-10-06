"""Confusable skeleton (UTS #39 style, trimmed to what phishing kits use against Latin brand names).

Both the observed name and every brand token are mapped through the same skeleton, then compared.
"""
from __future__ import annotations

import unicodedata

# Cyrillic / Greek / IPA look-alikes of Latin letters.
_SCRIPT = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "ѕ": "s", "і": "i",
    "ј": "j", "ӏ": "l", "ԁ": "d", "ɡ": "g", "ո": "n", "ν": "v", "ο": "o", "α": "a", "к": "k",
    "м": "m", "т": "t", "в": "b", "н": "h", "ı": "i", "ɩ": "i", "ƅ": "b", "ԛ": "q", "ԝ": "w",
    "ү": "y", "һ": "h", "ѡ": "w", "ɑ": "a", "ε": "e", "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
}
# Visual classes: every member collapses to one representative.
_CLASS = {"l": "i", "1": "i", "|": "i", "!": "i", "0": "o", "3": "e", "4": "a", "5": "s", "7": "t",
          "$": "s", "@": "a"}
_TABLE = str.maketrans({**_SCRIPT, **_CLASS})
_MULTI = (("rn", "m"), ("vv", "w"), ("cl", "d"))


def skeleton(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().translate(_TABLE)
    for a, b in _MULTI:
        s = s.replace(a, b)
    return s
