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


def linked_round(conn, tmp_path):
    """Contacts + Advance/Mains round with every exact match confirmed."""
    from marksapp.results import build_results
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    confirm_proposed(conn, rid)
    return rid, build_results(conn, rid)


def make_result(name="PALLAPU MEGHANA SRI", phone="+919876543201",
                exams=(("Advance Exam - 4", 41, 32, 17, 90), ("Mains Exam - 4", 62, 17, 16, 95))):
    from marksapp.results import ExamMarks, StudentResult
    from marksapp.values import parse_mark
    ems = []
    for i, (display, m, p, c, t) in enumerate(exams):
        ems.append(ExamMarks(exam_id=i + 1, display_name=display, exam_type=display.split(" - ")[0],
                             exam_number=4, mark_row_id=i + 1, maths=parse_mark(m), physics=parse_mark(p),
                             chemistry=parse_mark(c), total=parse_mark(t), total_in_file=parse_mark(t),
                             computed_total=parse_mark(t), absent_row=False, issues=[]))
    return StudentResult(student_id=1, name=name, phone=phone, stud_id="1", exams=ems, issues=[])


def image_only_copy(pdf_path, out_dir):
    """Re-create a PDF as pictures of its pages: like a scanned file, with no text layer."""
    import pymupdf as fitz
    src = fitz.open(str(pdf_path))
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=200)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("png"))
    path = out_dir / f"scanned-{pdf_path.name}"
    out.save(str(path))
    return path
