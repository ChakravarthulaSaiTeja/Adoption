"""A single mark: a number (negative allowed), absent (AB) or not available (NA).

Missing marks are never treated as 0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

MarkKind = Literal["num", "AB", "NA"]

_ABSENT_WORDS = {"AB", "ABSENT", "A"}


@dataclass(frozen=True)
class Mark:
    kind: MarkKind
    value: float | None = None

    def display(self) -> str:
        if self.kind != "num":
            return self.kind
        v = float(self.value)
        return str(int(v)) if v.is_integer() else repr(v)

    def encode(self) -> str:
        if self.kind == "num":
            return f"num:{float(self.value)!r}"
        return self.kind


NA = Mark("NA")
AB = Mark("AB")


def decode_mark(s: str) -> Mark:
    if s.startswith("num:"):
        return Mark("num", float(s[4:]))
    if s == "AB":
        return AB
    return NA


def parse_mark(raw: object) -> Mark:
    if raw is None or isinstance(raw, bool):
        return NA
    if isinstance(raw, (int, float)):
        f = float(raw)
        return NA if math.isnan(f) else Mark("num", f)
    text = str(raw).strip().replace("−", "-").upper()
    if not text:
        return NA
    if text in _ABSENT_WORDS:
        return AB
    try:
        f = float(text)
    except ValueError:
        return NA
    if math.isnan(f) or math.isinf(f):
        return NA
    return Mark("num", f)
