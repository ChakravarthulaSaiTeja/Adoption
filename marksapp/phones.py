"""Parent WhatsApp numbers: clean up what people type into a standard +91 form."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

_SCIENTIFIC = re.compile(r"^\d+(\.\d+)?[eE]\+?\d+$")
_DECIMAL_ZERO = re.compile(r"^\d+\.0+$")
_SEPARATORS = re.compile(r"[/,;&|]|\s+or\s+", re.IGNORECASE)


@dataclass(frozen=True)
class PhoneResult:
    ok: bool
    e164: str | None
    raw: str
    problem: str | None


def _bad(raw: str, problem: str) -> PhoneResult:
    return PhoneResult(False, None, raw, problem)


def normalise_phone(raw: object) -> PhoneResult:
    if raw is None or isinstance(raw, bool):
        return _bad("", "Missing")
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and math.isnan(raw):
            return _bad("", "Missing")
        text = str(int(raw))
    else:
        text = str(raw).strip()
        if _SCIENTIFIC.match(text) or _DECIMAL_ZERO.match(text):
            text = str(int(float(text)))
    if not text:
        return _bad("", "Missing")

    parts = [p for p in _SEPARATORS.split(text) if len(re.sub(r"\D", "", p)) >= 10]
    if len(parts) > 1:
        return _bad(text, "More than one number")

    plus = text.startswith("+") or text.lstrip("(").startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return _bad(text, "Missing")
    if not plus and digits.startswith("00"):
        plus, digits = True, digits[2:]  # "00" is the international prefix, same as "+"
    if plus:
        if digits.startswith("91"):
            digits = digits[2:]  # Indian number written with its country code: Indian rules below
        elif 8 <= len(digits) <= 15 and not digits.startswith("0"):
            return PhoneResult(True, "+" + digits, text, None)  # a parent abroad
        else:
            return _bad(text, "Not a valid international number")
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10:
        return _bad(text, "Must be 10 digits")
    if digits[0] not in "6789":
        return _bad(text, "Must start with 6, 7, 8 or 9")
    return PhoneResult(True, "+91" + digits, text, None)


def pretty_phone(e164: str) -> str:
    if e164 and e164.startswith("+91") and len(e164) == 13:
        return f"+91 {e164[3:8]} {e164[8:]}"
    return e164 or ""
