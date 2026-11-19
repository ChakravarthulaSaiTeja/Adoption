import pytest

from marksapp import audit
from marksapp.contacts import (ContactRow, add_student, apply_contact_diff, detect_contact_columns,
                               diff_contacts, list_students, shared_number_groups, update_student)
from marksapp.phones import normalise_phone
from tests.helpers import seed_contacts


def test_detect_columns():
    grid = [["Sl", "Student Name", "Section", "WhatsApp Number"], ["1", "Syed Afreen", "PR4", "9876543208"]]
    assert detect_contact_columns(grid) == (0, 1, 3, 2)
    assert detect_contact_columns([["a", "b"]]) == (None, None, None, None)


def test_first_import(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    s = {r["name"]: r for r in list_students(conn)}
    assert len(s) == 8
    assert s["Gorantla Sai Kartik"]["phone"] == "+919876543202"
    assert s["Syed Afreen"]["phone"] == "+919876543208"
    assert s["Kolluri Anjali"]["phone"] is None and s["Kolluri Anjali"]["phone_raw"] == "98765432"
    assert [len(g) for g in shared_number_groups(conn)] == [2]


def test_reimport_changes(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Syed Afreen"], stud_id="100000008")
    rows = [ContactRow(1, "SYED AFREEN", normalise_phone("9876543299"), ""),  # reordered/caps, new phone
            ContactRow(2, "New Student", normalise_phone("9876543300"), "")]
    d = diff_contacts(conn, rows)
    assert [r.name for r in d.new] == ["New Student"]
    assert d.phone_changed[0][0] == ids["Syed Afreen"]
    assert len(d.missing) == 7
    apply_contact_diff(conn, d, "c.xlsx", "h")
    afreen = conn.execute("select * from students where id=?", (ids["Syed Afreen"],)).fetchone()
    assert afreen["stud_id"] == "100000008" and afreen["phone"] == "+919876543299"
    assert conn.execute("select count(*) from students where active=0").fetchone()[0] == 7
    assert conn.execute("select count(*) from students").fetchone()[0] == 9  # nothing deleted


def test_reimport_reactivates(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Syed Afreen"], active=False)
    d = diff_contacts(conn, [ContactRow(1, "Syed Afreen", normalise_phone("9876543208"), "")])
    assert d.reactivated == [ids["Syed Afreen"]]


def test_invalid_new_number_never_overwrites_valid(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    d = diff_contacts(conn, [ContactRow(1, "Syed Afreen", normalise_phone("123"), "")])
    assert d.phone_changed == [] and len(d.bad_numbers) == 1
    apply_contact_diff(conn, d, "c.xlsx", "h")
    assert conn.execute("select phone from students where id=?", (ids["Syed Afreen"],)).fetchone()[0] == "+919876543208"


def test_duplicate_names_not_applied(conn):
    rows = [ContactRow(1, "Syed Afreen", normalise_phone("9876543208"), ""),
            ContactRow(2, "AFREEN SYED", normalise_phone("9876543209"), "")]
    d = diff_contacts(conn, rows)
    assert len(d.duplicate_names) == 1 and d.new == []


def test_row_without_name_is_invalid(conn):
    d = diff_contacts(conn, [ContactRow(1, "", normalise_phone("9876543208"), "")])
    assert len(d.invalid) == 1 and d.new == []


def test_update_student_guards(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Nakka Ravi Teja"], stud_id="100000005")
    with pytest.raises(ValueError):
        update_student(conn, ids["Nakka Ravi Kiran"], stud_id="100000005")
    with pytest.raises(ValueError):
        update_student(conn, ids["Nakka Ravi Kiran"], phone="123")
    assert any(r["action"] == "student_updated" for r in audit.recent(conn))


def test_add_student(conn):
    sid = add_student(conn, "Syed Afreen", "9876543208", "PR4")
    assert list_students(conn)[0]["id"] == sid
    with pytest.raises(ValueError):
        add_student(conn, "Bad Number", "12")
