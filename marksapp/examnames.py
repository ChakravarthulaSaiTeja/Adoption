"""Turn a raw test name ("JEE(Adv)/WTA-4") into the message heading ("Advance Exam - 4")."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExamName:
    exam_type: str
    number: int | None
    display: str
    sort_order: int


def suggest_exam_name(test_name: str | None, rules: list[list[str]]) -> ExamName:
    text = (test_name or "").strip()
    upper = text.upper()
    exam_type, order = (text or "Exam"), len(rules)
    for i, (keyword, type_name) in enumerate(rules):
        if keyword and keyword.upper() in upper:
            exam_type, order = type_name, i
            break
    numbers = re.findall(r"\d+", text)
    number = int(numbers[-1]) if numbers and order < len(rules) else None
    display = f"{exam_type} - {number}" if number is not None else exam_type
    return ExamName(exam_type, number, display, order)
