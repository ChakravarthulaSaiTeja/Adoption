"""Audit log: every import, link, approval, send and edit, with a timestamp."""
from __future__ import annotations

import json
import sqlite3

from marksapp.db import now_iso


def log(conn: sqlite3.Connection, action: str, **details) -> None:
    """Record an action. Inside an open transaction the row joins that
    transaction (so it is rolled back with it); otherwise it commits at once."""
    row = (now_iso(), action, json.dumps(details, default=str, ensure_ascii=False))
    sql = "INSERT INTO audit_log(ts, action, details) VALUES (?, ?, ?)"
    if conn.in_transaction:
        conn.execute(sql, row)
    else:
        with conn:
            conn.execute(sql, row)


def recent(conn: sqlite3.Connection, limit: int = 200) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
