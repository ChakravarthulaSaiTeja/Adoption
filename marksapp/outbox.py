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
    "sent": {"approved", "failed", "unknown"},  # unknown → sent: the owner checked it arrived
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
    allowed = sorted(_ALLOWED_FROM[new])
    with conn:
        # The status check is part of the write, so another session can't slip in between.
        cur = conn.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ? AND status = ? "
                           f"AND status IN ({','.join('?' * len(allowed))})",
                           (*values, message_id, old, *allowed))
        if cur.rowcount == 0:
            now = conn.execute("SELECT status FROM messages WHERE id = ?", (message_id,)).fetchone()
            if now is None:
                raise ValueError("Message not found — approve it first")
            raise ValueError(f"Cannot go from {now['status']} to {new}")
        extra = {}
        if new in ("sent", "accepted"):
            # Permanent history of what actually went out: never deleted or overwritten.
            m = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            conn.execute("INSERT INTO sent_log(message_id, round_id, student_id, phone, body, method, "
                         "api_message_id, sent_at) VALUES (?,?,?,?,?,?,?,?)",
                         (message_id, m["round_id"], m["student_id"], m["phone"], m["body"], m["method"],
                          m["api_message_id"], m["sent_at"] or now_iso()))
            extra = {"phone": m["phone"], "body_hash": m["body_hash"]}
        audit.log(conn, f"message_{new}", message_id=message_id, round_id=row["round_id"],
                  student_id=row["student_id"], previous=old, **extra,
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


def drop_stale_approvals(conn: sqlite3.Connection, round_id: int) -> int:
    """Drop every waiting approval whose number or text no longer matches. Returns how many."""
    from marksapp.messages import message_settings
    from marksapp.results import build_results
    ms = message_settings(conn)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    dropped = 0
    for rec in get_outbox(conn, round_id).values():
        if rec.status in ("approved", "failed") and not check_current(conn, rec, results.get(rec.student_id), ms):
            dropped += 1
    return dropped
