"""Contacts: upload the contact list, review changes, and edit students."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from marksapp.contacts import (add_student, apply_contact_diff, detect_contact_columns, diff_contacts,
                               list_students, parse_contacts, shared_number_groups, update_student)
from marksapp.phones import pretty_phone
from marksapp.readers.grid import NoTextInPdf, UnsupportedFile, file_hash, load_grid
from marksapp.settings import get_setting


def _column_label(grid, header_row, c) -> str:
    if header_row is not None and c < len(grid[header_row]) and grid[header_row][c]:
        return f"{grid[header_row][c]} (column {c + 1})"
    return f"Column {c + 1}"


def _upload(conn: sqlite3.Connection) -> None:
    st.subheader("Upload contact list")
    up = st.file_uploader("Excel, CSV or PDF with student names and WhatsApp numbers",
                          type=["xlsx", "xls", "csv", "pdf"], key="contacts_file")
    if up is None:
        return
    data = up.getvalue()
    try:
        grid = load_grid(data, up.name)
    except NoTextInPdf:
        st.error("This PDF is a scanned image. Please upload the Excel file or a text PDF.")
        return
    except UnsupportedFile as e:
        st.error(str(e))
        return
    if not grid:
        st.error("The file is empty.")
        return
    header_row, name_col, phone_col, section_col = detect_contact_columns(grid)
    width = max(len(r) for r in grid)
    cols = list(range(width))
    label = lambda c: _column_label(grid, header_row, c)
    c1, c2, c3 = st.columns(3)
    name_col = c1.selectbox("Name column", cols, index=name_col or 0, format_func=label, key="c_name")
    phone_col = c2.selectbox("WhatsApp number column", cols,
                             index=phone_col if phone_col is not None else min(1, width - 1),
                             format_func=label, key="c_phone")
    section_options = [None] + cols
    section_col = c3.selectbox("Section column (optional)", section_options,
                               index=section_options.index(section_col),
                               format_func=lambda c: "None" if c is None else label(c), key="c_sec")
    rows = parse_contacts(grid, header_row, name_col, phone_col, section_col)
    st.caption(f"{len(rows)} rows read. First five:")
    st.dataframe(pd.DataFrame([{"Name": r.name, "Number as typed": r.phone.raw,
                                "Cleaned": r.phone.e164 or f"⚠ {r.phone.problem}"} for r in rows[:5]]),
                 hide_index=True)

    d = diff_contacts(conn, rows)
    m = st.columns(4)
    m[0].metric("New students", len(d.new))
    m[1].metric("Changed numbers", len(d.phone_changed))
    m[2].metric("Will become inactive", len(d.missing))
    m[3].metric("Need attention", len(d.duplicate_names) + len(d.invalid) + len(d.bad_numbers))
    names = {s["id"]: s["name"] for s in list_students(conn, include_inactive=True)}
    if d.new:
        with st.expander(f"New students ({len(d.new)})"):
            st.write(", ".join(r.name for r in d.new))
    if d.phone_changed:
        with st.expander(f"Changed numbers ({len(d.phone_changed)})"):
            for sid, r, old in d.phone_changed:
                st.write(f"{names.get(sid)}: {pretty_phone(old or '') or 'none'} → {pretty_phone(r.phone.e164)}")
    if d.reactivated:
        with st.expander(f"Back on the list ({len(d.reactivated)})"):
            st.write(", ".join(names.get(i, "?") for i in d.reactivated))
    if d.missing:
        with st.expander(f"Not in this file — will become inactive, not deleted ({len(d.missing)})"):
            st.write(", ".join(names.get(i, "?") for i in d.missing))
    if d.duplicate_names:
        with st.expander(f"Same name more than once — NOT applied ({len(d.duplicate_names)})", expanded=True):
            for group in d.duplicate_names:
                st.write(" / ".join(f"{r.name} (row {r.line_no})" for r in group))
            st.caption("Fix these in the file, or add the students by hand below.")
    if d.invalid:
        with st.expander(f"Rows without a name — NOT applied ({len(d.invalid)})"):
            for r in d.invalid:
                st.write(f"Row {r.line_no}: {r.phone.raw}")
    if d.bad_numbers:
        with st.expander(f"Numbers to check ({len(d.bad_numbers)})", expanded=True):
            for r in d.bad_numbers:
                st.write(f"{r.name} (row {r.line_no}): '{r.phone.raw}' — {r.phone.problem}")
            st.caption("New students are saved without a number; fix it below. "
                       "A saved valid number is never replaced by a bad one.")
    if d.shared_numbers:
        with st.expander(f"Shared numbers ({len(d.shared_numbers)})"):
            for group in d.shared_numbers:
                st.write(" & ".join(group))
    if st.button("Apply changes", type="primary", key="contacts_apply"):
        apply_contact_diff(conn, d, up.name, file_hash(data))
        st.success("Contact list updated.")


def _student_list(conn: sqlite3.Connection) -> None:
    st.subheader("Students")
    show_inactive = st.checkbox("Show inactive students", key="show_inactive")
    search = st.text_input("Search by name", key="student_search").strip().lower()
    students = [s for s in list_students(conn, include_inactive=show_inactive)
                if search in s["name"].lower()]
    st.dataframe(pd.DataFrame([{
        "Name": s["name"], "WhatsApp": pretty_phone(s["phone"] or "") or f"⚠ {s['phone_raw'] or 'missing'}",
        "File ID": s["stud_id"] or "", "Section": s["section"] or "",
        "Active": "Yes" if s["active"] else "No"} for s in students]), hide_index=True)

    groups = shared_number_groups(conn)
    if groups and not get_setting(conn, "message")["include_name"]:
        pairs = "; ".join(" & ".join(s["name"] for s in g) for g in groups)
        st.warning(f"Some parents have more than one child on the list ({pairs}). Turn on "
                   "'Start each message with the student's name' in Settings so they can tell "
                   "the messages apart.")

    everyone = list_students(conn, include_inactive=True)
    if everyone:
        with st.expander("Edit a student"):
            by_id = {s["id"]: s for s in everyone}
            sid = st.selectbox("Student", list(by_id), format_func=lambda i: by_id[i]["name"], key="edit_pick")
            s = by_id[sid]
            with st.form(f"edit_{sid}"):
                name = st.text_input("Name", s["name"])
                phone = st.text_input("WhatsApp number", s["phone"] or s["phone_raw"] or "")
                section = st.text_input("Section", s["section"] or "")
                notes = st.text_input("Notes", s["notes"] or "")
                active = st.checkbox("Active", bool(s["active"]))
                unlink = st.checkbox(f"Unlink marks-file ID ({s['stud_id']})", disabled=not s["stud_id"])
                if st.form_submit_button("Save"):
                    fields = {"name": name, "section": section, "notes": notes, "active": active}
                    if phone.strip() != (s["phone"] or s["phone_raw"] or ""):
                        fields["phone"] = phone
                    if unlink:
                        fields["stud_id"] = None
                        fields["name_in_marks"] = None
                    try:
                        update_student(conn, sid, **fields)
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        st.success("Saved.")

    with st.expander("Add a student"):
        with st.form("add_student", clear_on_submit=True):
            name = st.text_input("Name")
            phone = st.text_input("WhatsApp number")
            section = st.text_input("Section (optional)")
            if st.form_submit_button("Add"):
                try:
                    add_student(conn, name, phone, section or None)
                except ValueError as e:
                    st.error(str(e))
                else:
                    st.success(f"Added {name}.")


def render(conn: sqlite3.Connection) -> None:
    st.title("Contacts")
    _upload(conn)
    st.divider()
    _student_list(conn)
