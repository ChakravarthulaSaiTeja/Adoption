"""Shared test helpers that build realistic state through the real code paths."""
from __future__ import annotations

from tests.fixtures import builders


def seed_contacts(conn, tmp_path) -> dict[str, int]:
    from marksapp.contacts import apply_contact_diff, detect_contact_columns, diff_contacts, parse_contacts
    from marksapp.readers.grid import file_hash, load_grid
    path = tmp_path / "contacts.xlsx"
    builders.write_contacts_xlsx(path)
    data = path.read_bytes()
    grid = load_grid(data, path.name)
    header_row, name_col, phone_col, section_col = detect_contact_columns(grid)
    rows = parse_contacts(grid, header_row, name_col, phone_col, section_col)
    apply_contact_diff(conn, diff_contacts(conn, rows), path.name, file_hash(data))
    return {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM students")}


def add_file(conn, round_id: int, path, via_ocr: bool = False) -> int:
    """Add one marks file to a round the way the upload page does."""
    from marksapp.examnames import suggest_exam_name
    from marksapp.readers.grid import file_hash, load_grid
    from marksapp.readers.marks_layout import parse_marks_grid
    from marksapp.rounds import add_exam
    from marksapp.settings import get_setting
    data = path.read_bytes()
    parsed = parse_marks_grid(load_grid(data, path.name))
    name = suggest_exam_name(parsed.test_name, get_setting(conn, "exam_rules"))
    return add_exam(conn, round_id, parsed, name, path.name, file_hash(data), via_ocr=via_ocr)


_seed_counter = [0]


def seed_round(conn, tmp_path, fmt: str = "xlsx", mains: bool = True) -> int:
    from marksapp.rounds import create_round
    _seed_counter[0] += 1
    files = builders.write_all_marks_files(tmp_path / f"round_files_{_seed_counter[0]}")
    rid = create_round(conn, f"Test round {_seed_counter[0]}")
    add_file(conn, rid, files[fmt])
    if mains:
        add_file(conn, rid, files["mains_pdf" if fmt == "pdf" else "mains_xlsx"])
    return rid


def confirm_proposed(conn, round_id: int) -> None:
    from marksapp.rounds import confirm_links, match_round
    confirm_links(conn, [(m.stud_id, m.student_id, m.names[0])
                         for m in match_round(conn, round_id) if m.status == "proposed"])
