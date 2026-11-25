import pytest

from marksapp.messages import message_settings
from marksapp.outbox import approve
from marksapp.readers.grid import NoTextInPdf, load_grid
from marksapp.readers.marks_layout import parse_marks_grid
from marksapp.readers.ocr import ocr_available, ocr_pdf_to_grid
from marksapp.results import build_results
from marksapp.rounds import create_round
from marksapp.ui.round_page import prepare_upload
from tests.fixtures import builders
from tests.helpers import confirm_proposed, image_only_copy, seed_contacts

needs_tess = pytest.mark.skipif(not ocr_available(), reason="Tesseract not installed")


@needs_tess
def test_scanned_copy_really_has_no_text(tmp_path, marks_files):
    scanned = image_only_copy(marks_files["pdf"], tmp_path)
    with pytest.raises(NoTextInPdf):
        load_grid(scanned.read_bytes(), scanned.name)


@needs_tess
def test_ocr_reads_most_ids(tmp_path, marks_files):
    scanned = image_only_copy(marks_files["pdf"], tmp_path)
    f = parse_marks_grid(ocr_pdf_to_grid(scanned.read_bytes()))
    ids = {r.stud_id for r in f.rows}
    assert len(ids & {r[0] for r in builders.SAMPLE_ROWS}) >= 6


@needs_tess
def test_ocr_upload_is_marked_and_never_bulk_approved(conn, tmp_path, marks_files):
    from marksapp.readers.grid import file_hash
    from marksapp.rounds import add_exam
    seed_contacts(conn, tmp_path)
    scanned = image_only_copy(marks_files["pdf"], tmp_path)
    data = scanned.read_bytes()
    up = prepare_upload(conn, data, scanned.name, None)
    assert up.error is None and up.via_ocr is True and up.parsed.rows
    rid = create_round(conn, "scanned")
    add_exam(conn, rid, up.parsed, up.name, scanned.name, file_hash(data), via_ocr=True)
    confirm_proposed(conn, rid)
    rr = build_results(conn, rid)
    assert rr.students and all("ocr" in [i.code for i in s.issues] for s in rr.students)
    assert approve(conn, rid, rr.students, message_settings(conn)) == []


def test_prepare_upload_without_tesseract(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("marksapp.readers.ocr.ocr_available", lambda: False)
    p = tmp_path / "s.pdf"
    builders.write_blank_pdf(p)
    assert "OCR is not installed" in prepare_upload(conn, p.read_bytes(), p.name, None).error
