"""New round: upload this round's marks files, confirm what was read, add them."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from marksapp.examnames import ExamName, suggest_exam_name
from marksapp.readers.grid import Grid, NoTextInPdf, UnsupportedFile, file_hash, load_grid
from marksapp.readers.marks_layout import (OPTIONAL, REQUIRED, LayoutNotFound, ParsedMarksFile,
                                           header_signature, parse_marks_grid)
from marksapp.rounds import (RoundLocked, add_exam, create_round, find_duplicate_exam, get_layout,
                             list_exams, list_rounds, remove_exam, round_locked, round_warnings, save_layout)
from marksapp.settings import get_setting

SCANNED_PDF = "This PDF is a scanned image. Scanned PDFs need OCR (stage 2)."
NO_TABLE = ("Couldn't find the marks table: no header row with a student ID and a name column. "
            "Map the columns by hand below.")
FIELD_LABELS = {"stud_id": "Student ID", "name": "Student name", "maths": "Maths", "physics": "Physics",
                "chemistry": "Chemistry", "section": "Section", "total": "Total"}


@dataclass
class UploadPreview:
    parsed: ParsedMarksFile | None
    name: ExamName | None
    duplicate: sqlite3.Row | None
    error: str | None
    via_ocr: bool
    grid: Grid | None = None


def _first_nonempty_row(grid: Grid) -> int:
    return next((i for i, r in enumerate(grid) if any(str(c).strip() for c in r)), 0)


def _scanned_pdf_grid(data: bytes) -> tuple[Grid | None, str | None]:
    """Stage 1 has no OCR; replaced in stage 2."""
    return None, SCANNED_PDF


def prepare_upload(conn: sqlite3.Connection, data: bytes, filename: str,
                   column_map: dict[str, int] | None, header_row: int | None = None) -> UploadPreview:
    via_ocr = False
    try:
        grid = load_grid(data, filename)
    except NoTextInPdf:
        grid, error = _scanned_pdf_grid(data)
        if grid is None:
            return UploadPreview(None, None, None, error, False)
        via_ocr = True
    except UnsupportedFile as e:
        return UploadPreview(None, None, None, str(e), False)
    if not grid:
        return UploadPreview(None, None, None, "The file is empty.", via_ocr, grid)

    parsed = None
    if column_map is not None:
        hr = header_row if header_row is not None else _first_nonempty_row(grid)
        parsed = parse_marks_grid(grid, column_map, hr)
    else:
        try:
            parsed = parse_marks_grid(grid)
            if parsed.missing_fields:
                saved = get_layout(conn, parsed.header_signature)
                if saved:
                    parsed = parse_marks_grid(grid, saved, parsed.header_row)
        except LayoutNotFound:
            for i, row in enumerate(grid[:30]):
                saved = get_layout(conn, header_signature(row))
                if saved:
                    parsed = parse_marks_grid(grid, saved, i)
                    break
    if parsed is None:
        return UploadPreview(None, None, None, NO_TABLE, via_ocr, grid)
    name = suggest_exam_name(parsed.test_name, get_setting(conn, "exam_rules"))
    duplicate = find_duplicate_exam(conn, file_hash(data), parsed.test_name, parsed.test_date)
    return UploadPreview(parsed, name, duplicate, None, via_ocr, grid)


def _pick_round(conn: sqlite3.Connection) -> int | None:
    open_rounds = [r for r in list_rounds(conn) if not round_locked(conn, r["id"])]
    options = [None] + [r["id"] for r in open_rounds]
    labels = {r["id"]: r["label"] for r in open_rounds}
    if "current_round" in st.session_state and st.session_state["current_round"] in options:
        index = options.index(st.session_state["current_round"])
    else:
        index = 1 if open_rounds else 0
    choice = st.selectbox("Round", options, index=index, key="round_pick",
                          format_func=lambda r: "➕ Start a new round" if r is None else labels[r])
    if choice is None:
        label = st.text_input("Name for the new round", f"Round of {date.today():%d-%b-%Y}", key="round_label")
        if st.button("Start round", type="primary", key="round_create"):
            st.session_state["current_round"] = create_round(conn, label.strip() or "Round")
            st.rerun()
        return None
    st.session_state["current_round"] = choice
    return choice


def _manual_mapping(grid: Grid, key: str) -> tuple[dict[str, int], int] | None:
    st.caption("Tell the app which column holds what. This is remembered for files with the same headers.")
    header_row = st.number_input("Header row number", 1, len(grid), _first_nonempty_row(grid) + 1,
                                 key=f"{key}_hr") - 1
    headers = grid[header_row]
    cols = list(range(max(len(r) for r in grid)))
    label = lambda c: f"{headers[c]} (column {c + 1})" if c < len(headers) and headers[c] else f"Column {c + 1}"
    cmap: dict[str, int] = {}
    cells = st.columns(4)
    for i, f in enumerate(REQUIRED + OPTIONAL):
        options = cols if f in REQUIRED else [None] + cols
        choice = cells[i % 4].selectbox(FIELD_LABELS[f], options, key=f"{key}_{f}",
                                        format_func=lambda c: "None" if c is None else label(c))
        if choice is not None:
            cmap[f] = choice
    if st.checkbox("Use this mapping", key=f"{key}_use"):
        return cmap, header_row
    return None


def _exam_name_inputs(conn: sqlite3.Connection, suggested: ExamName, key: str) -> ExamName:
    rules = get_setting(conn, "exam_rules")
    types = [t for _, t in rules]
    options = types + ["Other"]
    c1, c2, c3 = st.columns(3)
    idx = types.index(suggested.exam_type) if suggested.exam_type in types else len(types)
    exam_type = c1.selectbox("Exam type", options, index=idx, key=f"{key}_type")
    if exam_type == "Other":
        exam_type = c1.text_input("Type name", suggested.exam_type, key=f"{key}_other") or "Exam"
    number = c2.number_input("Exam number", 0, 999, suggested.number or 0, key=f"{key}_num")
    number = int(number) or None
    default = f"{exam_type} - {number}" if number else exam_type
    display = c3.text_input("Heading in the message", default, key=f"{key}_disp_{exam_type}_{number}")
    order = types.index(exam_type) if exam_type in types else len(types)
    return ExamName(exam_type, number, display.strip() or default, order)


def _one_file(conn: sqlite3.Connection, round_id: int, up, idx: int) -> None:
    key = f"f{idx}_{up.file_id if hasattr(up, 'file_id') else up.name}"
    data = up.getvalue()
    with st.container(border=True):
        st.markdown(f"**{up.name}**")
        preview = prepare_upload(conn, data, up.name, None)
        manual = None
        if preview.error and preview.grid:
            st.warning(preview.error)
            manual = _manual_mapping(preview.grid, key)
        elif preview.parsed is not None and preview.parsed.missing_fields:
            missing = ", ".join(FIELD_LABELS[f] for f in preview.parsed.missing_fields)
            st.warning(f"Couldn't find these columns: {missing}. Map the columns by hand.")
            manual = _manual_mapping(preview.grid, key)
        elif preview.error:
            st.error(preview.error)
            return
        if manual is not None:
            preview = prepare_upload(conn, data, up.name, manual[0], manual[1])
        p = preview.parsed
        if p is None or p.missing_fields:
            return
        if preview.via_ocr:
            st.warning("Read from a scanned PDF. Every student from this file will need checking one by one.")
        mx = {k: _max_text(v) for k, v in p.maxes.items()}
        st.caption(f"Test name: {p.test_name or '—'} · Test date: {p.test_date or '—'} · "
                   f"Max marks: Maths {mx['maths']}, Physics {mx['physics']}, "
                   f"Chemistry {mx['chemistry']}, Total {mx['total']}")
        name = _exam_name_inputs(conn, preview.name, key)
        st.write(f"**{len(p.rows)} students read.** First five:")
        st.dataframe(pd.DataFrame([{"ID": r.stud_id, "Name": r.name, "Section": r.section,
                                    "Maths": r.maths.display(), "Physics": r.physics.display(),
                                    "Chemistry": r.chemistry.display(), "Total": r.total_in_file.display()}
                                   for r in p.rows[:5]]), hide_index=True)
        if p.unreadable:
            with st.expander(f"⚠ {len(p.unreadable)} rows could not be read", expanded=True):
                for u in p.unreadable:
                    st.write(f"Row {u.row_no} ({u.reason}): {u.raw_text}")
        replace_id = None
        if preview.duplicate is not None:
            d = preview.duplicate
            st.warning(f"This looks like a file already imported: {d['display_name']} "
                       f"({d['filename']}, imported {d['imported_at'][:10]}).")
            if st.checkbox("Replace the earlier import", key=f"{key}_replace"):
                replace_id = d["id"]
        blocked = preview.duplicate is not None and replace_id is None
        if st.button("Add to round", type="primary", key=f"{key}_add", disabled=blocked):
            try:
                add_exam(conn, round_id, p, name, up.name, file_hash(data), via_ocr=preview.via_ocr,
                         replace_exam_id=replace_id)
            except RoundLocked:
                st.error("Messages from this round have already been sent. Start a new round for this file.")
                return
            if manual is not None:
                save_layout(conn, p.header_signature, manual[0])
            st.success(f"Added {name.display}.")
            st.rerun()


def _max_text(v: float | None) -> str:
    if v is None:
        return "?"
    return str(int(v)) if float(v).is_integer() else str(v)


def render(conn: sqlite3.Connection) -> None:
    st.title("New round")
    st.caption("Upload this round's marks files (for example the Advance and the Mains file). "
               "Nothing is sent from this page.")
    round_id = _pick_round(conn)
    if round_id is None:
        return
    locked = round_locked(conn, round_id)
    exams = list_exams(conn, round_id)
    st.subheader("Files in this round")
    if not exams:
        st.write("No files yet.")
    for e in exams:
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{e.display_name}** — {e.filename}" + (" (scanned)" if e.via_ocr else ""))
        if c2.button("Remove", key=f"rm_{e.id}", disabled=locked):
            remove_exam(conn, e.id)
            st.rerun()
    for w in round_warnings(conn, round_id):
        st.warning(w)
    if locked:
        st.info("Messages from this round have been sent, so its files can't change. Start a new round instead.")
        return
    st.subheader("Add files")
    files = st.file_uploader("Marks files (Excel, CSV or PDF)", type=["xlsx", "xls", "csv", "pdf"],
                             accept_multiple_files=True, key=f"marks_files_{round_id}")
    for i, up in enumerate(files or []):
        _one_file(conn, round_id, up, i)
    if exams:
        st.info("When all files are added, open **Needs attention** to confirm students.")
