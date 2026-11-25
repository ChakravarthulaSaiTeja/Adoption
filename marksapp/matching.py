"""Link rows in the marks files to students on the owner's list.

Safety rules (spec 6.5):
- A STUD_ID already linked to a student is matched by ID; the name is only a cross-check.
- Otherwise a link is only *proposed* for an exact name-key match with exactly one
  student on each side. Everything else goes to the owner for review.
- A fuzzy score never links anyone; it only lists candidates.
- Links are saved elsewhere (rounds.confirm_links), only after the owner confirms.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from marksapp.names import name_key, similarity

CANDIDATE_FLOOR = 70.0
CROSSCHECK_MIN = 85.0
MAX_CANDIDATES = 3

MatchStatus = Literal["linked", "proposed", "review", "not_found", "ignored"]


@dataclass(frozen=True)
class StudentRef:
    id: int
    name: str
    stud_id: str | None
    name_in_marks: str | None  # accepted spellings from marks files, one per line
    active: bool


@dataclass(frozen=True)
class RowRef:
    exam_id: int
    row_no: int
    stud_id: str
    name: str


@dataclass
class Candidate:
    student_id: int
    name: str
    score: float


@dataclass
class MatchResult:
    stud_id: str
    names: list[str]
    rows: list[RowRef]
    status: MatchStatus
    student_id: int | None = None
    candidates: list[Candidate] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    flagged_names: list[str] = field(default_factory=list)  # names that failed the cross-check


def _fuzzy(names: list[str], pool: list[StudentRef], exclude: set[int]) -> list[Candidate]:
    scored = []
    for s in pool:
        if s.id in exclude:
            continue
        score = max(similarity(n, s.name) for n in names)
        if score >= CANDIDATE_FLOOR:
            scored.append(Candidate(s.id, s.name, score))
    scored.sort(key=lambda c: (-c.score, c.name))
    return scored[:MAX_CANDIDATES]


def match_rows(rows: list[RowRef], students: list[StudentRef], ignored: set[str]) -> list[MatchResult]:
    groups: dict[str, list[RowRef]] = {}
    for r in rows:
        groups.setdefault(r.stud_id, []).append(r)

    by_stud_id = {s.stud_id: s for s in students if s.stud_id}
    pool = [s for s in students if s.active and not s.stud_id]

    # Name keys over every row in the round (linked ones too): a new ID that shares a name
    # with any other ID in the files is never proposed (spec 6.5 step 2).
    round_keys = Counter(name_key(g[0].name) for sid, g in groups.items() if sid not in ignored)

    results: list[MatchResult] = []
    for sid, group in groups.items():
        names = list(dict.fromkeys(r.name for r in group))
        m = MatchResult(stud_id=sid, names=names, rows=group, status="review")
        exams = Counter(r.exam_id for r in group)
        if any(n > 1 for n in exams.values()):
            m.reasons.append("Appears more than once in the same file")

        if sid in by_stud_id:
            s = by_stud_id[sid]
            m.status, m.student_id = "linked", s.id
            accepted = [s.name] + [a for a in (s.name_in_marks or "").split("\n") if a]
            for n in names:
                score = max(similarity(n, a) for a in accepted)
                if score < CROSSCHECK_MIN:
                    m.flagged_names.append(n)
                    m.reasons.append(f"Name in file ({n}) differs from saved name ({s.name})")
                    m.candidates = [Candidate(s.id, s.name, score)]
            if not s.active:
                m.reasons.append("Student is marked inactive")
            if m.reasons:
                m.status = "review"
        elif sid in ignored:
            m.status = "ignored"
        else:
            key = name_key(names[0])
            exact = [s for s in pool if name_key(s.name) == key]
            exact_c = [Candidate(s.id, s.name, 100.0) for s in exact]
            if m.reasons or len({name_key(n) for n in names}) > 1:
                if len({name_key(n) for n in names}) > 1:
                    m.reasons.append("Different names for the same ID across files")
                m.candidates = exact_c + _fuzzy(names, pool, {s.id for s in exact})
            elif len(exact) == 1 and round_keys[key] == 1:
                m.status, m.student_id, m.candidates = "proposed", exact[0].id, exact_c
            elif len(exact) > 1:
                m.reasons.append("Several students on your list have this name")
                m.candidates = exact_c
            elif len(exact) == 1:
                m.reasons.append("Another student in the file has the same name")
                m.candidates = exact_c
            else:
                m.candidates = _fuzzy(names, pool, set())
                if m.candidates:
                    m.reasons.append("Name not exactly on your list — pick the right student")
                else:
                    m.status = "not_found"
        results.append(m)

    # Safety net: no student may be held by two proposed/linked results.
    held = Counter(m.student_id for m in results if m.status in ("proposed", "linked"))
    for m in results:
        if m.status in ("proposed", "linked") and held[m.student_id] > 1:
            m.reasons.append("Matches more than one student in the file")
            if m.status == "proposed":
                m.student_id = None
            m.status = "review"
    return results
