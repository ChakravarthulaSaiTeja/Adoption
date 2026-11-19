"""App settings, stored as JSON in the settings table, with defaults."""
from __future__ import annotations

import copy
import json
import sqlite3
from typing import Any

from marksapp import audit

DEFAULTS: dict[str, Any] = {
    "exam_rules": [["ADV", "Advance Exam"], ["MAIN", "Mains Exam"]],
    "message": {
        "exam_block": "*{exam} Marks*\n\nMaths - {maths}\nPhysics - {physics}\n"
                      "Chemistry - {chemistry}\n\n*Total Marks - {total}*",
        "separator": "\n\n",
        "include_name": False,
        "name_line": "*{name}*",
    },
    "link_kind": "wa.me",
    "api": {"enabled": False, "api_version": "v24.0", "language": "en",
            "templates": {}, "pause_seconds": 2.0},
}


def get_setting(conn: sqlite3.Connection, key: str) -> Any:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return json.loads(row["value"])
    return copy.deepcopy(DEFAULTS.get(key))


def _put(conn: sqlite3.Connection, key: str, value: Any) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    _put(conn, key, value)
    audit.log(conn, "settings_changed", key=key)
