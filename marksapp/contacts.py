"""The owner's contact list: student names and parent WhatsApp numbers.

A re-uploaded list is compared with the saved one first; nothing changes until
the owner applies the differences. Students are never deleted, only made inactive.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from marksapp import audit
from marksapp.db import now_iso
from marksapp.names import name_key
from marksapp.phones import PhoneResult, normalise_phone
from marksapp.readers.grid import Grid, clean_id

_PHONE_WORDS = ("WHATSAPP", "MOBILE", "PHONE", "CONTACT", "NUMBER")
_EDITABLE = {"name", "phone", "stud_id", "name_in_marks", "section", "active", "notes"}


@dataclass
class ContactRow:
    line_no: int
    name: str
    phone: PhoneResult
    section: str


@dataclass
class ContactDiff:
    new: list[ContactRow] = field(default_factory=list)
    phone_changed: list[tuple[int, ContactRow, str | None]] = field(default_factory=list)
    reactivated: list[int] = field(default_factory=list)
    unchanged: list[int] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    duplicate_names: list[list[ContactRow]] = field(default_factory=list)
    invalid: list[ContactRow] = field(default_factory=list)
    bad_numbers: list[ContactRow] = field(default_factory=list)
    shared_numbers: list[list[str]] = field(default_factory=list)
    row_count: int = 0


def detect_contact_columns(grid: Grid) -> tuple[int | None, int | None, int | None, int | None]:
    for i, row in enumerate(grid):
        cells = [str(c).upper() for c in row]
        phone_col = next((c for c, v in enumerate(cells) if any(w in v for w in _PHONE_WORDS)), None)
        name_col = next((c for c, v in enumerate(cells) if "NAME" in v and c != phone_col), None)
        if name_col is None:
            name_col = next((c for c, v in enumerate(cells) if "STUDENT" in v and c != phone_col), None)
        if name_col is not None and phone_col is not None:
            section_col = next((c for c, v in enumerate(cells)
                                if "".join(ch for ch in v if ch.isalnum()) in ("SEC", "SECTION")), None)
            return i, name_col, phone_col, section_col
    return None, None, None, None


def parse_contacts(grid: Grid, header_row: int | None, name_col: int, phone_col: int,
                   section_col: int | None = None) -> list[ContactRow]:
    start = 0 if header_row is None else header_row + 1
    get = lambda row, c: str(row[c]).strip() if c is not None and c < len(row) and row[c] is not None else ""
    rows = []
    for i in range(start, len(grid)):
        row = grid[i]
        name = " ".join(get(row, name_col).split())
        phone_raw = get(row, phone_col)
        if not name and not phone_raw:
            continue
        rows.append(ContactRow(i + 1, name, normalise_phone(phone_raw), get(row, section_col)))
    return rows


def diff_contacts(conn: sqlite3.Connection, rows: list[ContactRow]) -> ContactDiff:
    d = ContactDiff(row_count=len(rows))
    saved_by_key: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for s in conn.execute("SELECT * FROM students"):
        saved_by_key[s["name_key"]].append(s)

    named = []
    for r in rows:
        (named if r.name else d.invalid).append(r)
    by_key: dict[str, list[ContactRow]] = defaultdict(list)
    for r in named:
        by_key[name_key(r.name)].append(r)

    matched_ids: set[int] = set()
    applied_rows: list[ContactRow] = []
    for key, group in by_key.items():
        saved = saved_by_key.get(key, [])
        if len(group) > 1 or len(saved) > 1:
            d.duplicate_names.append(group)
            matched_ids.update(s["id"] for s in saved)
            continue
        r = group[0]
        applied_rows.append(r)
        if not saved:
            d.new.append(r)
            if not r.phone.ok:
                d.bad_numbers.append(r)
            continue
        s = saved[0]
        matched_ids.add(s["id"])
        changed = False
        if r.phone.ok and r.phone.e164 != s["phone"]:
            d.phone_changed.append((s["id"], r, s["phone"]))
            changed = True
        elif not r.phone.ok:
            d.bad_numbers.append(r)
        if not s["active"]:
            d.reactivated.append(s["id"])
        elif not changed:
            d.unchanged.append(s["id"])

    d.missing = [s["id"] for group in saved_by_key.values() for s in group
                 if s["active"] and s["id"] not in matched_ids]

    by_phone: dict[str, list[str]] = defaultdict(list)
    for r in applied_rows:
        if r.phone.ok:
            by_phone[r.phone.e164].append(r.name)
    d.shared_numbers = [names for names in by_phone.values() if len(names) > 1]
    return d


def apply_contact_diff(conn: sqlite3.Connection, diff: ContactDiff, filename: str, file_hash: str) -> None:
    now = now_iso()
    with conn:
        for r in diff.new:
            conn.execute(
                "INSERT INTO students(name, name_key, phone, phone_raw, section, active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (r.name, name_key(r.name), r.phone.e164, r.phone.raw, r.section or None, now, now))
        for sid, r, _old in diff.phone_changed:
            conn.execute("UPDATE students SET phone = ?, phone_raw = ?, updated_at = ? WHERE id = ?",
                         (r.phone.e164, r.phone.raw, now, sid))
        for sid in diff.reactivated:
            conn.execute("UPDATE students SET active = 1, updated_at = ? WHERE id = ?", (now, sid))
        for sid in diff.missing:
            conn.execute("UPDATE students SET active = 0, updated_at = ? WHERE id = ?", (now, sid))
        conn.execute("INSERT INTO contact_imports(filename, file_hash, imported_at, row_count) VALUES (?, ?, ?, ?)",
                     (filename, file_hash, now, diff.row_count))
        audit.log(conn, "contacts_imported", filename=filename, new=len(diff.new),
                  phone_changed=len(diff.phone_changed), reactivated=len(diff.reactivated),
                  made_inactive=len(diff.missing), duplicates_not_applied=len(diff.duplicate_names),
                  invalid=len(diff.invalid), bad_numbers=len(diff.bad_numbers))


def add_student(conn: sqlite3.Connection, name: str, phone_raw: str, section: str | None = None) -> int:
    name = " ".join(str(name).split())
    if not name:
        raise ValueError("Name is required")
    phone = normalise_phone(phone_raw)
    if not phone.ok:
        raise ValueError(phone.problem)
    now = now_iso()
    with conn:
        cur = conn.execute(
            "INSERT INTO students(name, name_key, phone, phone_raw, section, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (name, name_key(name), phone.e164, phone.raw, section or None, now, now))
        audit.log(conn, "student_added", student_id=cur.lastrowid, name=name, phone=phone.e164)
    return cur.lastrowid


def update_student(conn: sqlite3.Connection, student_id: int, **fields) -> None:
    unknown = set(fields) - _EDITABLE
    if unknown:
        raise ValueError(f"Cannot edit: {', '.join(sorted(unknown))}")
    current = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if current is None:
        raise ValueError("Student not found")
    updates: dict[str, object] = {}
    if "name" in fields:
        name = " ".join(str(fields["name"]).split())
        if not name:
            raise ValueError("Name is required")
        updates["name"], updates["name_key"] = name, name_key(name)
    if "phone" in fields:
        phone = normalise_phone(fields["phone"])
        if not phone.ok:
            raise ValueError(phone.problem)
        updates["phone"], updates["phone_raw"] = phone.e164, phone.raw
    if "stud_id" in fields:
        sid = fields["stud_id"]
        sid = clean_id(sid) if sid not in (None, "") else None
        if sid is not None:
            holder = conn.execute("SELECT id, name FROM students WHERE stud_id = ? AND id != ?",
                                  (sid, student_id)).fetchone()
            if holder is not None:
                raise ValueError(f"ID already linked to {holder['name']}")
        updates["stud_id"] = sid
    for key in ("name_in_marks", "section", "notes"):
        if key in fields:
            updates[key] = fields[key] or None
    if "active" in fields:
        updates["active"] = 1 if fields["active"] else 0
    if not updates:
        return
    updates["updated_at"] = now_iso()
    with conn:
        conn.execute(f"UPDATE students SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
                     (*updates.values(), student_id))
        audit.log(conn, "student_updated", student_id=student_id, fields=sorted(fields),
                  old_phone=current["phone"], new_phone=updates.get("phone", current["phone"]),
                  old_stud_id=current["stud_id"], new_stud_id=updates.get("stud_id", current["stud_id"]))


def list_students(conn: sqlite3.Connection, include_inactive: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM students" + ("" if include_inactive else " WHERE active = 1")
    return conn.execute(sql + " ORDER BY name COLLATE NOCASE").fetchall()


def shared_number_groups(conn: sqlite3.Connection) -> list[list[sqlite3.Row]]:
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for s in conn.execute("SELECT * FROM students WHERE active = 1 AND phone IS NOT NULL ORDER BY name"):
        groups[s["phone"]].append(s)
    return [g for g in groups.values() if len(g) > 1]


def _shared_ok(conn: sqlite3.Connection) -> dict[str, list[int]]:
    from marksapp.settings import get_setting
    return get_setting(conn, "shared_numbers_ok") or {}


def unconfirmed_shared_numbers(conn: sqlite3.Connection) -> list[list[sqlite3.Row]]:
    """Numbers used by two or more active students that the owner hasn't confirmed as one parent.
    A confirmation covers exactly the students sharing the number at the time; adding another
    student to that number makes it unconfirmed again."""
    ok = _shared_ok(conn)
    return [g for g in shared_number_groups(conn)
            if ok.get(g[0]["phone"]) != sorted(s["id"] for s in g)]


def confirm_shared_number(conn: sqlite3.Connection, phone: str) -> None:
    from marksapp.settings import set_setting
    ids = sorted(s["id"] for s in conn.execute(
        "SELECT id FROM students WHERE active = 1 AND phone = ?", (phone,)))
    ok = _shared_ok(conn)
    ok[phone] = ids
    set_setting(conn, "shared_numbers_ok", ok)
    audit.log(conn, "shared_number_confirmed", phone=phone, student_ids=ids)
