"""Rounds of exams: stored files and rows, confirmed links, ignored IDs, layouts."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from marksapp import audit
from marksapp.db import now_iso
from marksapp.examnames import ExamName
from marksapp.matching import MatchResult, RowRef, StudentRef, match_rows
from marksapp.readers.marks_layout import ParsedMarksFile
from marksapp.values import Mark, decode_mark

LOCKING_STATES = {"sent", "accepted", "sending", "unknown"}


class RoundLocked(Exception):
    pass


@dataclass
class ExamRec:
    id: int
    round_id: int
    display_name: str
    exam_type: str
    exam_number: int | None
    sort_order: int
    test_name: str | None
    test_date: str | None
    maxes: dict[str, float | None]
    filename: str
    file_hash: str
    via_ocr: bool


@dataclass
class MarkRowRec:
    id: int
    exam_id: int
    row_no: int
    stud_id: str
    name_in_file: str
    section: str | None
    maths: Mark
    physics: Mark
    chemistry: Mark
    total_in_file: Mark
    total_choice: str | None
    edited: bool


def _exam(r: sqlite3.Row) -> ExamRec:
    return ExamRec(
        id=r["id"], round_id=r["round_id"], display_name=r["display_name"], exam_type=r["exam_type"],
        exam_number=r["exam_number"], sort_order=r["sort_order"], test_name=r["test_name"],
        test_date=r["test_date"],
        maxes={"maths": r["max_maths"], "physics": r["max_physics"],
               "chemistry": r["max_chemistry"], "total": r["max_total"]},
        filename=r["filename"], file_hash=r["file_hash"], via_ocr=bool(r["via_ocr"]))


def _mark_row(r: sqlite3.Row) -> MarkRowRec:
    return MarkRowRec(
        id=r["id"], exam_id=r["exam_id"], row_no=r["row_no"], stud_id=r["stud_id"],
        name_in_file=r["name_in_file"], section=r["section"], maths=decode_mark(r["maths"]),
        physics=decode_mark(r["physics"]), chemistry=decode_mark(r["chemistry"]),
        total_in_file=decode_mark(r["total_in_file"]), total_choice=r["total_choice"],
        edited=bool(r["edited"]))


def create_round(conn: sqlite3.Connection, label: str) -> int:
    with conn:
        cur = conn.execute("INSERT INTO rounds(label, created_at) VALUES (?, ?)", (label, now_iso()))
        audit.log(conn, "round_created", round_id=cur.lastrowid, label=label)
    return cur.lastrowid


def list_rounds(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM rounds ORDER BY id DESC").fetchall()


def round_locked(conn: sqlite3.Connection, round_id: int) -> bool:
    marks = ",".join("?" * len(LOCKING_STATES))
    row = conn.execute(f"SELECT 1 FROM messages WHERE round_id = ? AND status IN ({marks}) LIMIT 1",
                       (round_id, *LOCKING_STATES)).fetchone()
    return row is not None


def _clear_unsent(conn: sqlite3.Connection, round_id: int) -> None:
    marks = ",".join("?" * len(LOCKING_STATES))
    conn.execute(f"DELETE FROM messages WHERE round_id = ? AND status NOT IN ({marks})",
                 (round_id, *LOCKING_STATES))


def find_duplicate_exam(conn: sqlite3.Connection, file_hash: str, test_name: str | None,
                        test_date: str | None) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM exams WHERE file_hash = ? "
        "OR (? IS NOT NULL AND ? IS NOT NULL AND test_name = ? AND test_date = ?) ORDER BY id LIMIT 1",
        (file_hash, test_name, test_date, test_name, test_date)).fetchone()


def _exam_round(conn: sqlite3.Connection, exam_id: int) -> int:
    row = conn.execute("SELECT round_id FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if row is None:
        raise ValueError("Exam not found")
    return row["round_id"]


def add_exam(conn: sqlite3.Connection, round_id: int, parsed: ParsedMarksFile, name: ExamName,
             filename: str, file_hash: str, via_ocr: bool = False,
             replace_exam_id: int | None = None) -> int:
    if round_locked(conn, round_id):
        raise RoundLocked("Messages from this round have already been sent")
    if replace_exam_id is not None and round_locked(conn, _exam_round(conn, replace_exam_id)):
        raise RoundLocked("The earlier import belongs to a round that has already been sent")
    mx = parsed.maxes
    with conn:
        if replace_exam_id is not None:
            _clear_unsent(conn, _exam_round(conn, replace_exam_id))
            conn.execute("DELETE FROM exams WHERE id = ?", (replace_exam_id,))
        _clear_unsent(conn, round_id)
        cur = conn.execute(
            "INSERT INTO exams(round_id, test_name, test_date, display_name, exam_type, exam_number, "
            "sort_order, max_maths, max_physics, max_chemistry, max_total, filename, file_hash, via_ocr, "
            "imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (round_id, parsed.test_name, parsed.test_date, name.display, name.exam_type, name.number,
             name.sort_order, mx.get("maths"), mx.get("physics"), mx.get("chemistry"), mx.get("total"),
             filename, file_hash, int(via_ocr), now_iso()))
        exam_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO marks(exam_id, row_no, stud_id, name_in_file, section, maths, physics, chemistry, "
            "total_in_file) VALUES (?,?,?,?,?,?,?,?,?)",
            [(exam_id, r.row_no, r.stud_id, r.name, r.section or None, r.maths.encode(),
              r.physics.encode(), r.chemistry.encode(), r.total_in_file.encode()) for r in parsed.rows])
        conn.executemany(
            "INSERT INTO unreadable_rows(exam_id, row_no, raw_text, reason) VALUES (?,?,?,?)",
            [(exam_id, u.row_no, u.raw_text, u.reason) for u in parsed.unreadable])
        audit.log(conn, "exam_added", round_id=round_id, exam_id=exam_id, display_name=name.display,
                  filename=filename, rows=len(parsed.rows), unreadable=len(parsed.unreadable),
                  via_ocr=via_ocr, replaced_exam_id=replace_exam_id)
    return exam_id


def remove_exam(conn: sqlite3.Connection, exam_id: int) -> None:
    round_id = _exam_round(conn, exam_id)
    if round_locked(conn, round_id):
        raise RoundLocked("Messages from this round have already been sent")
    with conn:
        _clear_unsent(conn, round_id)
        conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
        audit.log(conn, "exam_removed", round_id=round_id, exam_id=exam_id)


def list_exams(conn: sqlite3.Connection, round_id: int) -> list[ExamRec]:
    rows = conn.execute("SELECT * FROM exams WHERE round_id = ? "
                        "ORDER BY sort_order, exam_number, id", (round_id,)).fetchall()
    return [_exam(r) for r in rows]


def round_rows(conn: sqlite3.Connection, round_id: int) -> list[tuple[ExamRec, MarkRowRec]]:
    exams = {e.id: e for e in list_exams(conn, round_id)}
    rows = conn.execute(
        "SELECT m.* FROM marks m JOIN exams e ON e.id = m.exam_id WHERE e.round_id = ? "
        "ORDER BY e.sort_order, e.exam_number, e.id, m.row_no", (round_id,)).fetchall()
    return [(exams[r["exam_id"]], _mark_row(r)) for r in rows]


def round_warnings(conn: sqlite3.Connection, round_id: int) -> list[str]:
    numbered = [e for e in list_exams(conn, round_id) if e.exam_number is not None]
    if len({e.exam_number for e in numbered}) > 1:
        return ["Exam numbers differ in this round: " + ", ".join(e.display_name for e in numbered)]
    return []


def _students(conn: sqlite3.Connection) -> list[StudentRef]:
    return [StudentRef(r["id"], r["name"], r["stud_id"], r["name_in_marks"], bool(r["active"]))
            for r in conn.execute("SELECT * FROM students")]


def ignored_ids(conn: sqlite3.Connection) -> set[str]:
    return {r["stud_id"] for r in conn.execute("SELECT stud_id FROM ignored_ids")}


def match_round(conn: sqlite3.Connection, round_id: int) -> list[MatchResult]:
    rows = [RowRef(e.id, m.row_no, m.stud_id, m.name_in_file) for e, m in round_rows(conn, round_id)]
    return match_rows(rows, _students(conn), ignored_ids(conn))


def confirm_links(conn: sqlite3.Connection, links: list[tuple[str, int, str]]) -> None:
    stud_ids = [l[0] for l in links]
    student_ids = [l[1] for l in links]
    if len(set(stud_ids)) != len(stud_ids):
        raise ValueError("The same file ID was linked to two students")
    if len(set(student_ids)) != len(student_ids):
        raise ValueError("The same student was linked to two file IDs")
    for stud_id, student_id, _ in links:
        s = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if s is None:
            raise ValueError("Student not found")
        if s["stud_id"] and s["stud_id"] != stud_id:
            raise ValueError(f"{s['name']} is already linked to ID {s['stud_id']}")
        holder = conn.execute("SELECT name FROM students WHERE stud_id = ? AND id != ?",
                              (stud_id, student_id)).fetchone()
        if holder is not None:
            raise ValueError(f"ID {stud_id} is already linked to {holder['name']}")
    with conn:
        for stud_id, student_id, name_in_file in links:
            conn.execute("UPDATE students SET stud_id = ?, name_in_marks = ?, updated_at = ? WHERE id = ?",
                         (stud_id, name_in_file, now_iso(), student_id))
            conn.execute("DELETE FROM ignored_ids WHERE stud_id = ?", (stud_id,))
            audit.log(conn, "link_confirmed", stud_id=stud_id, student_id=student_id,
                      name_in_file=name_in_file)


def accept_name(conn: sqlite3.Connection, student_id: int, name_in_file: str) -> None:
    with conn:
        conn.execute("UPDATE students SET name_in_marks = ?, updated_at = ? WHERE id = ?",
                     (name_in_file, now_iso(), student_id))
        audit.log(conn, "name_accepted", student_id=student_id, name_in_file=name_in_file)


def ignore_ids(conn: sqlite3.Connection, items: list[tuple[str, str]]) -> None:
    with conn:
        for stud_id, name in items:
            conn.execute("INSERT OR REPLACE INTO ignored_ids(stud_id, name_in_file, created_at) VALUES (?,?,?)",
                         (stud_id, name, now_iso()))
            audit.log(conn, "id_ignored", stud_id=stud_id, name_in_file=name)


def unignore_id(conn: sqlite3.Connection, stud_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM ignored_ids WHERE stud_id = ?", (stud_id,))
        audit.log(conn, "id_unignored", stud_id=stud_id)


def save_layout(conn: sqlite3.Connection, signature: str, column_map: dict[str, int]) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO layouts(signature, column_map) VALUES (?, ?)",
                     (signature, json.dumps(column_map)))


def get_layout(conn: sqlite3.Connection, signature: str) -> dict[str, int] | None:
    row = conn.execute("SELECT column_map FROM layouts WHERE signature = ?", (signature,)).fetchone()
    return json.loads(row["column_map"]) if row else None
