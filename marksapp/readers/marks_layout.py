"""Find the marks table in a grid and read one MarksRow per student.

Every non-empty row after the first student row ends up either as a MarksRow
or as an UnreadableRow, so no student is ever dropped silently.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from marksapp.readers.grid import Grid, cell_text, clean_id
from marksapp.values import NA, Mark, parse_mark

REQUIRED = ("stud_id", "name", "maths", "physics", "chemistry")
OPTIONAL = ("section", "total")
MAX_FIELDS = ("maths", "physics", "chemistry", "total")

_LABELS = {
    "stud_id": {"STUDID", "STUDENTID", "ROLLNO", "ROLLNUMBER", "ADMNO", "ADMISSIONNO", "HTNO"},
    "section": {"SEC", "SECTION"},
    "total": {"TOT", "TOTAL", "TOTALMARKS"},
    "maths": {"MAT", "MATH", "MATHS", "MATHEMATICS"},
    "physics": {"PHY", "PHYSICS"},
    "chemistry": {"CHE", "CHEM", "CHEMISTRY"},
}
_ID_SHAPE = re.compile(r"^[A-Za-z0-9/\-]+$")  # any length: roll numbers can be 1, 2, ...
_TEST_NAME = re.compile(r"^test\s*name\s*[:\-]?\s*(.*)$", re.IGNORECASE)
_TEST_DATE = re.compile(r"^test\s*date\s*[:\-]?\s*(.*)$", re.IGNORECASE)
_NUMBER = re.compile(r"^\d+(\.\d+)?$")


@dataclass
class MarksRow:
    row_no: int
    stud_id: str
    name: str
    section: str
    maths: Mark
    physics: Mark
    chemistry: Mark
    total_in_file: Mark


@dataclass
class UnreadableRow:
    row_no: int
    raw_text: str
    reason: str


@dataclass
class ParsedMarksFile:
    test_name: str | None
    test_date: str | None
    header_row: int
    column_map: dict[str, int]
    maxes: dict[str, float | None]
    rows: list[MarksRow] = field(default_factory=list)
    unreadable: list[UnreadableRow] = field(default_factory=list)
    header_signature: str = ""
    missing_fields: list[str] = field(default_factory=list)


class LayoutNotFound(Exception):
    pass


def _norm(cell: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(cell).upper())


def _label_and_max(cell: str) -> tuple[str, float | None]:
    n = _norm(cell)
    m = re.match(r"^(.*?)(\d+)$", n)
    if m and m.group(1):
        return m.group(1), float(m.group(2))
    return n, None


def _field_for(cell: str) -> str | None:
    label, _ = _label_and_max(cell)
    if not label:
        return None
    for name, labels in _LABELS.items():
        if label in labels:
            return name
    if "NAME" in label:
        return "name"
    return None


def _cell(row: list[str], col: int) -> str:
    return row[col] if 0 <= col < len(row) else ""


def header_signature(cells: list[str]) -> str:
    return hashlib.sha1("|".join(_norm(c) for c in cells).encode()).hexdigest()


def detect_columns(grid: Grid) -> tuple[int, dict[str, int]]:
    for i, row in enumerate(grid):
        found: dict[str, int] = {}
        for c, cell in enumerate(row):
            f = _field_for(cell)
            if f and f not in found:
                found[f] = c
        if "stud_id" in found and "name" in found:
            return i, found
    raise LayoutNotFound("Could not find a header row with a student ID and a name column")


def _header_value(grid: Grid, pattern: re.Pattern, stop: int) -> str | None:
    for row in grid[: max(stop, 0)] if stop >= 0 else grid:
        for c, cell in enumerate(row):
            m = pattern.match(cell.strip())
            if m:
                value = m.group(1).strip()
                if value:
                    return value
                rest = [x for x in row[c + 1:] if x.strip()]
                return rest[0].strip() if rest else None
    return None


def _maxes(grid: Grid, header_row: int, column_map: dict[str, int]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for f in MAX_FIELDS:
        col = column_map.get(f)
        value = None
        if col is not None and header_row >= 0:
            _, value = _label_and_max(_cell(grid[header_row], col))
            below_is_student = (header_row + 1 < len(grid) and "stud_id" in column_map
                                and "name" in column_map and _is_data_row(grid[header_row + 1], column_map))
            if value is None and header_row + 1 < len(grid) and not below_is_student:
                below = _cell(grid[header_row + 1], col).strip()
                if _NUMBER.match(below):
                    value = float(below)
        out[f] = value
    return out


def _is_data_row(row: list[str], cm: dict[str, int]) -> bool:
    sid = clean_id(_cell(row, cm["stud_id"]))
    return bool(_ID_SHAPE.match(sid) and any(ch.isdigit() for ch in sid)
                and _cell(row, cm["name"]).strip())


def parse_marks_grid(grid: Grid, column_map: dict[str, int] | None = None,
                     header_row: int | None = None) -> ParsedMarksFile:
    grid = [[c if isinstance(c, str) else cell_text(c) for c in row] for row in grid]
    if column_map is None:
        detected_row, column_map = detect_columns(grid)
        header_row = detected_row if header_row is None else header_row
    elif header_row is None:
        try:
            header_row, _ = detect_columns(grid)
        except LayoutNotFound:
            header_row = -1

    signature = header_signature(grid[header_row] if header_row >= 0 else [])
    parsed = ParsedMarksFile(
        test_name=_header_value(grid, _TEST_NAME, header_row),
        test_date=_header_value(grid, _TEST_DATE, header_row),
        header_row=header_row,
        column_map=dict(column_map),
        maxes=_maxes(grid, header_row, column_map),
        header_signature=signature,
        missing_fields=[f for f in REQUIRED if f not in column_map],
    )
    if parsed.missing_fields:
        return parsed

    cm = column_map
    in_data = False
    for i in range(header_row + 1, len(grid)):
        row = grid[i]
        if not any(c.strip() for c in row):
            continue
        if _field_for(_cell(row, cm["stud_id"])) == "stud_id":
            in_data = False  # a repeated header (e.g. on a new PDF page)
            continue
        if _is_data_row(row, cm):
            in_data = True
            get = lambda f: _cell(row, cm[f]) if f in cm else ""
            parsed.rows.append(MarksRow(
                row_no=i + 1,
                stud_id=clean_id(get("stud_id")),
                name=" ".join(get("name").split()),
                section=get("section").strip(),
                maths=parse_mark(get("maths")),
                physics=parse_mark(get("physics")),
                chemistry=parse_mark(get("chemistry")),
                total_in_file=parse_mark(get("total")) if "total" in cm else NA,
            ))
        else:
            if not in_data and not _cell(row, cm["stud_id"]).strip() and not _cell(row, cm["name"]).strip():
                continue  # part of the header (max marks, sub-headings): no ID and no name
            sid = clean_id(_cell(row, cm["stud_id"]))
            ok_id = bool(_ID_SHAPE.match(sid) and any(ch.isdigit() for ch in sid))
            parsed.unreadable.append(UnreadableRow(
                row_no=i + 1,
                raw_text=" | ".join(c for c in row if c.strip()),
                reason="No name" if ok_id else "No student ID",
            ))
    return parsed
