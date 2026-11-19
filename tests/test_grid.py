import pytest

from marksapp.readers.grid import NoTextInPdf, UnsupportedFile, clean_id, file_hash, grid_lines, load_grid
from tests.fixtures import builders


@pytest.mark.parametrize("fmt", ["xlsx", "csv", "pdf"])
def test_sample_loads(marks_files, fmt):
    p = marks_files[fmt]
    grid = load_grid(p.read_bytes(), p.name)
    lines = grid_lines(grid)
    assert any("Test Name: JEE(Adv)/WTA-4" in line for line in lines)
    flat = [c for row in grid for c in row]
    assert "100000003" in flat
    assert "MUDDANA VENKATA SAI SRINIVAS RAO" in flat  # wrapped PDF cell joined with a space
    assert "-7" in flat


def test_ids_normalised_across_formats():
    assert clean_id(268435197.0) == "268435197"
    assert clean_id(268435197) == "268435197"
    assert clean_id("268435197.0") == "268435197"
    assert clean_id("2.68435197E8") == "268435197"
    assert clean_id(" 0012345 ") == "12345"
    assert clean_id("PR-0042") == "PR-0042"  # non-numeric kept as is
    assert clean_id(None) == ""


def test_unsupported():
    with pytest.raises(UnsupportedFile):
        load_grid(b"x", "marks.docx")


def test_pdf_without_text(tmp_path):
    p = tmp_path / "scan.pdf"
    builders.write_blank_pdf(p)
    with pytest.raises(NoTextInPdf):
        load_grid(p.read_bytes(), p.name)


def test_file_hash_stable():
    assert file_hash(b"abc") == file_hash(b"abc") != file_hash(b"abd")
