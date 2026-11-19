"""Delivery reports per round, and each student's marks and message history."""
from __future__ import annotations

import io
import sqlite3

import pandas as pd

from marksapp.outbox import get_outbox
from marksapp.phones import pretty_phone
from marksapp.results import build_results, compute_exam_marks
from marksapp.rounds import _exam, _mark_row

STATUS_LABELS = {"approved": "Pending", "failed": "Failed", "sending": "Sending",
                 "unknown": "Unknown — check", "sent": "Sent", "accepted": "Sent", "skipped": "Skipped"}
REPORT_COLUMNS = ["Student", "WhatsApp", "Status", "Method", "Sent at", "Attempts", "Error"]
HISTORY_COLUMNS = ["Round", "Exam", "Test date", "Maths", "Physics", "Chemistry", "Total"]
LOG_COLUMNS = ["Round", "Status", "WhatsApp", "Method", "Sent at", "Message"]


def round_report(conn: sqlite3.Connection, round_id: int) -> pd.DataFrame:
    out = get_outbox(conn, round_id)
    rows = []
    for s in build_results(conn, round_id).students:
        rec = out.get(s.student_id)
        rows.append({
            "Student": s.name,
            "WhatsApp": pretty_phone((rec.phone if rec and rec.phone else s.phone) or ""),
            "Status": STATUS_LABELS.get(rec.status, rec.status) if rec else "Pending",
            "Method": (rec.method or "") if rec else "",
            "Sent at": (rec.sent_at or "") if rec else "",
            "Attempts": rec.attempts if rec else 0,
            "Error": (rec.error or "") if rec else "",
        })
    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def round_counts(conn: sqlite3.Connection, round_id: int) -> dict[str, int]:
    counts = {"Sent": 0, "Failed": 0, "Pending": 0, "Skipped": 0, "Unknown — check": 0}
    for status in round_report(conn, round_id)["Status"]:
        counts[status] = counts.get(status, 0) + 1
    return counts


def report_xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def student_history(conn: sqlite3.Connection, student_id: int) -> pd.DataFrame:
    s = conn.execute("SELECT stud_id FROM students WHERE id = ?", (student_id,)).fetchone()
    if s is None or not s["stud_id"]:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    rows = conn.execute(
        "SELECT m.*, r.label AS round_label, e.id AS e_id FROM marks m JOIN exams e ON e.id = m.exam_id "
        "JOIN rounds r ON r.id = e.round_id WHERE m.stud_id = ? "
        "ORDER BY r.id DESC, e.sort_order, e.exam_number, e.id", (s["stud_id"],)).fetchall()
    out = []
    for r in rows:
        exam = _exam(conn.execute("SELECT * FROM exams WHERE id = ?", (r["e_id"],)).fetchone())
        em = compute_exam_marks(exam, _mark_row(r))
        out.append({"Round": r["round_label"], "Exam": exam.display_name, "Test date": exam.test_date or "",
                    "Maths": em.maths.display(), "Physics": em.physics.display(),
                    "Chemistry": em.chemistry.display(), "Total": em.total.display()})
    return pd.DataFrame(out, columns=HISTORY_COLUMNS)


def message_log(conn: sqlite3.Connection, student_id: int) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT m.*, r.label AS round_label FROM messages m JOIN rounds r ON r.id = m.round_id "
        "WHERE m.student_id = ? ORDER BY m.id DESC", (student_id,)).fetchall()
    return pd.DataFrame([{
        "Round": r["round_label"], "Status": STATUS_LABELS.get(r["status"], r["status"]),
        "WhatsApp": pretty_phone(r["phone"] or ""), "Method": r["method"] or "",
        "Sent at": r["sent_at"] or "", "Message": r["body"]} for r in rows], columns=LOG_COLUMNS)
