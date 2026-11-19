from streamlit.testing.v1 import AppTest

from marksapp.ui.round_page import prepare_upload
from tests.fixtures import builders
from tests.helpers import seed_contacts, seed_round


def attention_script():
    from marksapp.ui.attention_page import render
    from marksapp.ui.common import get_conn
    render(get_conn())


def round_script():
    from marksapp.ui.common import get_conn
    from marksapp.ui.round_page import render
    render(get_conn())


def test_prepare_upload_reads_sample(conn, marks_files):
    p = marks_files["pdf"]
    up = prepare_upload(conn, p.read_bytes(), p.name, None)
    assert up.error is None and up.name.display == "Advance Exam - 4" and len(up.parsed.rows) == 8
    assert up.duplicate is None and up.via_ocr is False


def test_prepare_upload_flags_duplicate(conn, tmp_path, marks_files):
    seed_round(conn, tmp_path, mains=False)
    p = marks_files["xlsx"]
    assert prepare_upload(conn, p.read_bytes(), p.name, None).duplicate is not None


def test_prepare_upload_scanned_pdf(conn, tmp_path):
    p = tmp_path / "s.pdf"
    builders.write_blank_pdf(p)
    assert "scanned" in prepare_upload(conn, p.read_bytes(), p.name, None).error


def test_prepare_upload_uses_saved_layout(conn):
    from marksapp.readers.marks_layout import parse_marks_grid
    from marksapp.rounds import save_layout
    g = [["Roll", "Student", "M", "P", "C", "Grand"], ["A123", "SYED AFREEN", "12", "8", "5", "25"]]
    data = "\n".join(",".join(r) for r in g).encode()
    first = prepare_upload(conn, data, "odd.csv", None)
    assert first.parsed is None and "student ID" in first.error and first.grid
    cmap = {"stud_id": 0, "name": 1, "maths": 2, "physics": 3, "chemistry": 4, "total": 5}
    manual = prepare_upload(conn, data, "odd.csv", cmap)
    assert len(manual.parsed.rows) == 1
    save_layout(conn, manual.parsed.header_signature, cmap)
    again = prepare_upload(conn, data, "odd.csv", None)
    assert again.error is None and len(again.parsed.rows) == 1


def test_round_page_renders(app_env, conn, tmp_path):
    seed_round(conn, tmp_path)
    at = AppTest.from_function(round_script).run(timeout=30)
    assert not at.exception


def test_attention_save_links(app_env, conn, tmp_path):
    seed_contacts(conn, tmp_path)
    seed_round(conn, tmp_path)
    at = AppTest.from_function(attention_script).run(timeout=30)
    assert not at.exception
    at.button(key="save_links").click().run(timeout=30)
    assert not at.exception
    assert conn.execute("select count(*) from students where stud_id is not null").fetchone()[0] == 6
