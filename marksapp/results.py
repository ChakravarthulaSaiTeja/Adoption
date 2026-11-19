"""Per-student results for a round: marks per exam, totals, and every issue to review."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from marksapp import audit
from marksapp.matching import MatchResult
from marksapp.rounds import ExamRec, MarkRowRec, list_exams, match_round, round_rows
from marksapp.values import AB, NA, Mark, decode_mark, parse_mark

SUBJECTS = (("Maths", "maths"), ("Physics", "physics"), ("Chemistry", "chemistry"))
EDITABLE_FIELDS = ("maths", "physics", "chemistry", "total_in_file")


@dataclass
class Issue:
    code: str
    text: str
    blocking: bool


@dataclass
class ExamMarks:
    exam_id: int
    display_name: str
    exam_type: str
    exam_number: int | None
    mark_row_id: int | None
    maths: Mark
    physics: Mark
    chemistry: Mark
    total: Mark
    total_in_file: Mark
    computed_total: Mark
    absent_row: bool
    issues: list[Issue] = field(default_factory=list)


@dataclass
class StudentResult:
    student_id: int
    name: str
    phone: str | None
    stud_id: str
    exams: list[ExamMarks]
    issues: list[Issue]

    @property
    def blocking(self) -> bool:
        return any(i.blocking for i in self.issues)

    @property
    def status(self) -> Literal["ready", "review"]:
        return "review" if self.issues else "ready"


@dataclass
class RoundResults:
    students: list[StudentResult]
    links_to_confirm: list[MatchResult]
    not_found: list[MatchResult]
    ignored: list[MatchResult]
    not_in_any_file: list[sqlite3.Row]
    unreadable: list[sqlite3.Row]


def _fmt(v: float | None) -> str:
    return Mark("num", v).display() if v is not None else "?"


def compute_exam_marks(exam: ExamRec, row: MarkRowRec | None) -> ExamMarks:
    name = exam.display_name
    base = dict(exam_id=exam.id, display_name=name, exam_type=exam.exam_type,
                exam_number=exam.exam_number)
    if row is None:
        return ExamMarks(**base, mark_row_id=None, maths=AB, physics=AB, chemistry=AB, total=AB,
                         total_in_file=NA, computed_total=AB, absent_row=True,
                         issues=[Issue("absent", f"Absent from {name}? Confirm before sending", False)])

    issues: list[Issue] = []
    values = {key: getattr(row, key) for _, key in SUBJECTS}
    for label, key in SUBJECTS:
        m, mx = values[key], exam.maxes.get(key)
        if m.kind == "NA":
            issues.append(Issue("subject_missing", f"{label} mark missing in {name} (shown as NA)", False))
        elif m.kind == "num" and mx is not None and not (-mx <= m.value <= mx):
            issues.append(Issue("out_of_range",
                                f"{label} {m.display()} is outside the allowed range in {name} (max {_fmt(mx)})",
                                True))

    kinds = {m.kind for m in values.values()}
    computed = NA
    if kinds == {"AB"}:
        total = computed = AB
        issues.append(Issue("absent", f"Absent from {name}? Confirm before sending", False))
    elif "NA" in kinds:
        total = NA
    elif "AB" in kinds:
        total = NA
        for label, key in SUBJECTS:
            if values[key].kind == "AB":
                issues.append(Issue("subject_absent", f"{label} marked AB in {name}", False))
    else:
        computed = Mark("num", sum(m.value for m in values.values()))
        file_total = row.total_in_file
        if row.total_choice == "file" and file_total.kind == "num":
            total = file_total
        elif row.total_choice == "sum":
            total = computed
        else:
            total = computed
            if file_total.kind == "num" and abs(file_total.value - computed.value) > 1e-9:
                issues.append(Issue(
                    "total_mismatch",
                    f"Total in file ({file_total.display()}) does not match sum of subjects "
                    f"({computed.display()}) in {name} — choose one", True))
        max_total = exam.maxes.get("total")
        if max_total is not None and total.kind == "num" and total.value > max_total:
            issues.append(Issue("total_over_max",
                                f"Total {total.display()} is above the maximum {_fmt(max_total)} in {name}", True))

    return ExamMarks(**base, mark_row_id=row.id, maths=values["maths"], physics=values["physics"],
                     chemistry=values["chemistry"], total=total, total_in_file=row.total_in_file,
                     computed_total=computed, absent_row=False, issues=issues)


def build_results(conn: sqlite3.Connection, round_id: int) -> RoundResults:
    exams = list_exams(conn, round_id)
    rows_by_stud: dict[str, dict[int, MarkRowRec]] = {}
    for exam, row in round_rows(conn, round_id):
        rows_by_stud.setdefault(row.stud_id, {}).setdefault(exam.id, row)
    matches = match_round(conn, round_id)
    students = conn.execute("SELECT * FROM students ORDER BY name COLLATE NOCASE").fetchall()
    linked_ids = {s["stud_id"] for s in students if s["stud_id"]}

    links_to_confirm = [m for m in matches if m.status == "proposed"
                        or (m.status == "review" and m.stud_id not in linked_ids)]
    review_by_student = {m.student_id: m for m in matches
                         if m.status == "review" and m.stud_id in linked_ids}
    ocr_exams = {e.id for e in exams if e.via_ocr}

    results: list[StudentResult] = []
    for s in students if exams else []:
        sid = s["stud_id"]
        if not sid or not (s["active"] or sid in rows_by_stud):
            continue
        rows = rows_by_stud.get(sid, {})
        exam_marks = [compute_exam_marks(e, rows.get(e.id)) for e in exams]
        issues: list[Issue] = []
        m = review_by_student.get(s["id"])
        if m is not None:
            issues += [Issue("match", r, True) for r in m.reasons if "inactive" not in r]
        if not s["active"]:
            issues.append(Issue("inactive", "Student is marked inactive — reactivate in Contacts to send", True))
        if not s["phone"]:
            issues.append(Issue("no_phone", "No valid WhatsApp number", True))
        if any(e.id in ocr_exams and e.id in rows for e in exams):
            issues.append(Issue("ocr", "Read from a scanned PDF — check every mark against the file", False))
        for em in exam_marks:
            issues += em.issues
        results.append(StudentResult(student_id=s["id"], name=s["name"], phone=s["phone"], stud_id=sid,
                                     exams=exam_marks, issues=issues))

    mentioned = {m.student_id for m in links_to_confirm if m.student_id} | {
        c.student_id for m in links_to_confirm for c in m.candidates}
    not_in_any_file = [s for s in students
                       if s["active"] and not s["stud_id"] and s["id"] not in mentioned]
    unreadable = conn.execute(
        "SELECT u.*, e.display_name, e.filename FROM unreadable_rows u JOIN exams e ON e.id = u.exam_id "
        "WHERE e.round_id = ? ORDER BY e.sort_order, u.row_no", (round_id,)).fetchall()
    return RoundResults(
        students=results,
        links_to_confirm=links_to_confirm,
        not_found=[m for m in matches if m.status == "not_found"],
        ignored=[m for m in matches if m.status == "ignored"],
        not_in_any_file=not_in_any_file,
        unreadable=unreadable,
    )


def set_total_choice(conn: sqlite3.Connection, mark_row_id: int, choice: Literal["file", "sum"]) -> None:
    if choice not in ("file", "sum"):
        raise ValueError("Choice must be 'file' or 'sum'")
    with conn:
        conn.execute("UPDATE marks SET total_choice = ? WHERE id = ?", (choice, mark_row_id))
        audit.log(conn, "total_choice_set", mark_row_id=mark_row_id, choice=choice)


def edit_mark(conn: sqlite3.Connection, mark_row_id: int,
              field_name: Literal["maths", "physics", "chemistry", "total_in_file"], raw: str) -> None:
    if field_name not in EDITABLE_FIELDS:
        raise ValueError(f"Cannot edit {field_name}")
    row = conn.execute(f"SELECT {field_name} FROM marks WHERE id = ?", (mark_row_id,)).fetchone()
    if row is None:
        raise ValueError("Marks row not found")
    old, new = decode_mark(row[0]), parse_mark(raw)
    with conn:
        conn.execute(f"UPDATE marks SET {field_name} = ?, edited = 1 WHERE id = ?", (new.encode(), mark_row_id))
        audit.log(conn, "mark_edited", mark_row_id=mark_row_id, field=field_name,
                  old=old.display(), new=new.display())
