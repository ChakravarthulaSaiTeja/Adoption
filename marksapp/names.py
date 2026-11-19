"""Student names: clean-up, order-free keys and a similarity score.

A similarity score only ever suggests candidates for the owner to pick from;
it never links a student on its own (see matching.py).
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

_SEPARATORS = re.compile(r"[.,\-_'\n\t]")
INITIALS_CAP = 90.0


def clean_name(raw: object) -> str:
    if raw is None:
        return ""
    text = _SEPARATORS.sub(" ", str(raw)).upper()
    return " ".join(text.split())


def name_key(raw: object) -> str:
    return " ".join(sorted(clean_name(raw).split()))


def _expand_initials(words: list[str], other: list[str]) -> list[str] | None:
    """Replace single letters in `words` with distinct unused words of `other`."""
    initials = [w for w in words if len(w) == 1]
    if not initials:
        return None
    available = list(other)
    for w in words:
        if len(w) > 1 and w in available:
            available.remove(w)
    expanded = []
    for w in words:
        if len(w) == 1:
            match = next((o for o in available if len(o) > 1 and o.startswith(w)), None)
            if match is None:
                return None
            available.remove(match)
            expanded.append(match)
        else:
            expanded.append(w)
    return expanded


def similarity(a: str, b: str) -> float:
    ca, cb = clean_name(a), clean_name(b)
    if not ca or not cb:
        return 0.0
    best = float(fuzz.token_sort_ratio(ca, cb))
    wa, wb = ca.split(), cb.split()
    for x, y in ((wa, wb), (wb, wa)):
        expanded = _expand_initials(x, y)
        if expanded is not None:
            score = min(INITIALS_CAP, float(fuzz.token_sort_ratio(" ".join(expanded), " ".join(y))))
            best = max(best, score)
    return best


def title_name(raw: str) -> str:
    return " ".join(w.capitalize() for w in str(raw).split())
