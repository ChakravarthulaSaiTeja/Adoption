import pytest

from marksapp.matching import MatchResult
from marksapp.rounds import (RoundLocked, add_exam, confirm_links, create_round, find_duplicate_exam,
                             get_layout, ignore_ids, list_exams, list_rounds, match_round, remove_exam,
                             round_locked, round_rows, round_warnings, save_layout, unignore_id)
from tests.fixtures import builders
from tests.helpers import add_file, seed_contacts, seed_round


def _insert_message(conn, rid, status):
    sid = conn.execute("select id from students limit 1").fetchone()[0]
    with conn:
        conn.execute("insert into messages(round_id,student_id,phone,body,body_hash,status) values (?,?,?,?,?,?)",
                     (rid, sid, "+91", "b", "h", status))


def test_add_and_order(conn, tmp_path):
    rid = create_round(conn, "r")
    files = builders.write_all_marks_files(tmp_path / "f")
    add_file(conn, rid, files["mains_xlsx"])  # added first on purpose
    add_file(conn, rid, files["xlsx"])
    assert [e.display_name for e in list_exams(conn, rid)] == ["Advance Exam - 4", "Mains Exam - 4"]
    assert list_exams(conn, rid)[1].maxes["total"] == 300
    assert len(round_rows(conn, rid)) == 16
    assert list_rounds(conn)[0]["id"] == rid


def test_duplicate_detection(conn, tmp_path):
    rid = seed_round(conn, tmp_path, mains=False)
    e = list_exams(conn, rid)[0]
    assert find_duplicate_exam(conn, e.file_hash, None, None)["id"] == e.id
    assert find_duplicate_exam(conn, "other", "JEE(Adv)/WTA-4", "17-August-2026")["id"] == e.id
    assert find_duplicate_exam(conn, "other", None, None) is None


def test_locked_after_send(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path, mains=False)
    assert not round_locked(conn, rid)
    _insert_message(conn, rid, "sent")
    assert round_locked(conn, rid)
    with pytest.raises(RoundLocked):
        remove_exam(conn, list_exams(conn, rid)[0].id)
    files = builders.write_all_marks_files(tmp_path / "late")
    with pytest.raises(RoundLocked):
        add_file(conn, rid, files["mains_xlsx"])


def test_adding_file_clears_approvals(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path, mains=False)
    _insert_message(conn, rid, "approved")
    add_file(conn, rid, builders.write_all_marks_files(tmp_path / "m")["mains_xlsx"])
    assert conn.execute("select count(*) from messages where round_id=?", (rid,)).fetchone()[0] == 0


def test_remove_exam(conn, tmp_path):
    rid = seed_round(conn, tmp_path)
    remove_exam(conn, list_exams(conn, rid)[1].id)
    assert [e.display_name for e in list_exams(conn, rid)] == ["Advance Exam - 4"]
    assert len(round_rows(conn, rid)) == 8


def test_confirm_links_all_or_nothing(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    with pytest.raises(ValueError):
        confirm_links(conn, [("1", ids["Syed Afreen"], "SYED AFREEN"), ("2", ids["Syed Afreen"], "X")])
    with pytest.raises(ValueError):
        confirm_links(conn, [("1", ids["Syed Afreen"], "SYED AFREEN"), ("1", ids["Kolluri Anjali"], "X")])
    assert conn.execute("select count(*) from students where stud_id is not null").fetchone()[0] == 0


def test_confirm_links_rejects_existing_conflicts(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    confirm_links(conn, [("1", ids["Syed Afreen"], "SYED AFREEN")])
    with pytest.raises(ValueError):
        confirm_links(conn, [("2", ids["Syed Afreen"], "SYED AFREEN")])  # already has another ID
    with pytest.raises(ValueError):
        confirm_links(conn, [("1", ids["Kolluri Anjali"], "KOLLURI ANJALI")])  # ID held by Afreen
    row = conn.execute("select stud_id, name_in_marks from students where id=?", (ids["Syed Afreen"],)).fetchone()
    assert tuple(row) == ("1", "SYED AFREEN")


def test_links_carry_to_next_round(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    r1 = seed_round(conn, tmp_path)
    proposed = [m for m in match_round(conn, r1) if m.status == "proposed"]
    assert len(proposed) == 6
    confirm_links(conn, [(m.stud_id, m.student_id, m.names[0]) for m in proposed])
    r2 = seed_round(conn, tmp_path)
    by_id = {m.stud_id: m for m in match_round(conn, r2)}
    assert all(by_id[m.stud_id].status == "linked" for m in proposed)


def test_ignore(conn, tmp_path):
    rid = seed_round(conn, tmp_path, mains=False)
    ignore_ids(conn, [("100000001", "PALLAPU MEGHANA SRI")])
    assert {m.stud_id: m.status for m in match_round(conn, rid)}["100000001"] == "ignored"
    unignore_id(conn, "100000001")
    assert {m.stud_id: m.status for m in match_round(conn, rid)}["100000001"] == "not_found"


def test_layout_roundtrip(conn):
    assert get_layout(conn, "sig") is None
    save_layout(conn, "sig", {"stud_id": 0})
    assert get_layout(conn, "sig") == {"stud_id": 0}


def test_round_warns_when_exam_numbers_differ(conn, tmp_path):
    rid = seed_round(conn, tmp_path, mains=False)  # Advance 4
    assert round_warnings(conn, rid) == []
    p = tmp_path / "mains5.xlsx"
    builders.write_xlsx(builders.marks_grid(test_name="JEE(Main)/WTM-5", maxes=(100, 100, 100, 300),
                                            rows=builders.MAINS_ROWS), p)
    add_file(conn, rid, p)
    assert round_warnings(conn, rid) == ["Exam numbers differ in this round: Advance Exam - 4, Mains Exam - 5"]
