"""Approved messages and their send status.

A message can only be sent from an approved row, and only while a freshly
built copy (same number, same text) still matches what the owner approved.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import quote

from marksapp import audit
from marksapp.db import now_iso
from marksapp.messages import MessageSettings, content_hash, render_message
from marksapp.results import StudentResult
from marksapp.rounds import LOCKING_STATES

_ALLOWED_FROM = {
    "sent": {"approved", "failed"},
    "failed": {"approved", "failed", "sending"},
    "sending": {"approved", "failed"},
    "accepted": {"sending"},
    "unknown": {"sending"},
    "skipped": {"approved", "failed"},
}


@dataclass
class OutboxRec:
    id: int
    round_id: int
    student_id: int
    phone: str
    body: str
    body_hash: str
    status: str
    method: str | None
    api_message_id: str | None
    error: str | None
    approved_at: str | None
    sent_at: str | None
    attempts: int


def _rec(r: sqlite3.Row) -> OutboxRec:
    return OutboxRec(**{k: r[k] for k in OutboxRec.__dataclass_fields__})


def get_outbox(conn: sqlite3.Connection, round_id: int) -> dict[int, OutboxRec]:
    rows = conn.execute("SELECT * FROM messages WHERE round_id = ?", (round_id,)).fetchall()
    return {r["student_id"]: _rec(r) for r in rows}


def approve(conn: sqlite3.Connection, round_id: int, results: list[StudentResult], ms: MessageSettings,
            *, allow_review: bool = False) -> list[int]:
    existing = get_outbox(conn, round_id)
    approved: list[int] = []
    now = now_iso()
    with conn:
        for r in results:
            if r.blocking or not r.phone or (r.status != "ready" and not allow_review):
                continue
            ex = existing.get(r.student_id)
            if ex is not None and ex.status in LOCKING_STATES:
                continue
            body = render_message(r, ms)
            conn.execute(
                "INSERT INTO messages(round_id, student_id, phone, body, body_hash, status, approved_at) "
                "VALUES (?, ?, ?, ?, ?, 'approved', ?) "
                "ON CONFLICT(round_id, student_id) DO UPDATE SET phone = excluded.phone, "
                "body = excluded.body, body_hash = excluded.body_hash, status = 'approved', "
                "approved_at = excluded.approved_at, error = NULL",
                (round_id, r.student_id, r.phone, body, content_hash(r.phone, body), now))
            audit.log(conn, "approved", round_id=round_id, student_id=r.student_id,
                      phone=r.phone, after_review=r.status != "ready")
            approved.append(r.student_id)
    return approved


def skip(conn: sqlite3.Connection, round_id: int, student_ids: list[int]) -> None:
    existing = get_outbox(conn, round_id)
    with conn:
        for sid in student_ids:
            ex = existing.get(sid)
            if ex is not None and ex.status in LOCKING_STATES:
                continue
            conn.execute(
                "INSERT INTO messages(round_id, student_id, phone, body, body_hash, status) "
                "VALUES (?, ?, '', '', '', 'skipped') "
                "ON CONFLICT(round_id, student_id) DO UPDATE SET status = 'skipped'",
                (round_id, sid))
            audit.log(conn, "skipped", round_id=round_id, student_id=sid)


def check_current(conn: sqlite3.Connection, rec: OutboxRec, result: StudentResult | None,
                  ms: MessageSettings) -> bool:
    """True if the approved text and number still match; otherwise drop the approval."""
    if (result is not None and not result.blocking and result.phone
            and content_hash(result.phone, render_message(result, ms)) == rec.body_hash):
        return True
    with conn:
        conn.execute("DELETE FROM messages WHERE id = ? AND status IN ('approved', 'failed')", (rec.id,))
        audit.log(conn, "approval_cleared_changed", round_id=rec.round_id, student_id=rec.student_id)
    return False


def _move(conn: sqlite3.Connection, message_id: int, new: str, *, count_attempt: bool, **updates) -> None:
    row = conn.execute("SELECT status, round_id, student_id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise ValueError("Message not found — approve it first")
    old = row["status"]
    if old not in _ALLOWED_FROM[new]:
        raise ValueError(f"Cannot go from {old} to {new}")
    if count_attempt and not (new == "failed" and old == "sending"):
        updates["attempts"] = None  # marker: increment
    sets = ["status = ?"]
    values: list[object] = [new]
    for k, v in updates.items():
        if k == "attempts":
            sets.append("attempts = attempts + 1")
        else:
            sets.append(f"{k} = ?")
            values.append(v)
    with conn:
        conn.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", (*values, message_id))
        audit.log(conn, f"message_{new}", message_id=message_id, round_id=row["round_id"],
                  student_id=row["student_id"], previous=old,
                  **{k: v for k, v in updates.items() if k != "attempts"})


def mark_sent(conn: sqlite3.Connection, message_id: int, method: str = "phone") -> None:
    _move(conn, message_id, "sent", count_attempt=True, sent_at=now_iso(), method=method, error=None)


def mark_failed(conn: sqlite3.Connection, message_id: int, error: str) -> None:
    _move(conn, message_id, "failed", count_attempt=True, error=error)


def mark_sending(conn: sqlite3.Connection, message_id: int) -> None:
    _move(conn, message_id, "sending", count_attempt=True, method="api")


def mark_accepted(conn: sqlite3.Connection, message_id: int, api_message_id: str) -> None:
    _move(conn, message_id, "accepted", count_attempt=False, api_message_id=api_message_id,
          sent_at=now_iso(), error=None)


def mark_unknown(conn: sqlite3.Connection, message_id: int, error: str) -> None:
    _move(conn, message_id, "unknown", count_attempt=False, error=error)


def reset_for_resend(conn: sqlite3.Connection, message_id: int) -> None:
    row = conn.execute("SELECT status, round_id, student_id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if row is None or row["status"] not in ("sent", "accepted", "unknown"):
        raise ValueError("Only sent or unknown messages can be sent again")
    with conn:
        conn.execute("UPDATE messages SET status = 'approved' WHERE id = ?", (message_id,))
        audit.log(conn, "resend_requested", message_id=message_id, round_id=row["round_id"],
                  student_id=row["student_id"], previous=row["status"])


def recover_interrupted(conn: sqlite3.Connection) -> int:
    with conn:
        n = conn.execute("UPDATE messages SET status = 'unknown', "
                         "error = 'Interrupted while sending — check WhatsApp' WHERE status = 'sending'").rowcount
        if n:
            audit.log(conn, "recovered_interrupted", count=n)
    return n


def phone_link(phone_e164: str, body: str, kind: str) -> str:
    digits = phone_e164.lstrip("+")
    text = quote(body, safe="")
    if kind == "web":
        return f"https://web.whatsapp.com/send?phone={digits}&text={text}"
    if kind == "desktop":
        return f"whatsapp://send?phone={digits}&text={text}"
    return f"https://wa.me/{digits}?text={text}"
