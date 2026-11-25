from marksapp.matching import RowRef, StudentRef, match_rows


def S(id, name, stud_id=None, alt=None, active=True):
    return StudentRef(id, name, stud_id, alt, active)


def R(stud_id, name, exam=1, row=1):
    return RowRef(exam, row, stud_id, name)


def test_exact_reordered_name_is_proposed():
    [m] = match_rows([R("1", "PALLAPU MEGHANA SRI")], [S(10, "Meghana Sri Pallapu")], set())
    assert (m.status, m.student_id) == ("proposed", 10)


def test_linked_by_id_ignores_format():
    [m] = match_rows([R("1", "PALLAPU MEGHANA SRI")], [S(10, "Meghana Sri Pallapu", "1")], set())
    assert (m.status, m.reasons) == ("linked", [])


def test_linked_name_differs_needs_review():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(10, "Meghana Sri Pallapu", "1")], set())
    assert m.status == "review" and m.student_id == 10 and "differs" in m.reasons[0]


def test_name_in_marks_satisfies_crosscheck():
    [m] = match_rows([R("1", "PALLAPU MEGHANA SRI")], [S(10, "Meghana", "1", alt="PALLAPU MEGHANA SRI")], set())
    assert m.status == "linked"


def test_fuzzy_never_proposed():
    [m] = match_rows([R("2", "GORANTLA SAI KARTHIK")], [S(11, "Gorantla Sai Kartik")], set())
    assert m.status == "review" and m.student_id is None and m.candidates[0].student_id == 11


def test_near_identical_different_names_are_never_proposed():
    [m] = match_rows([R("7", "KOLLURI ANJANI")], [S(12, "Kolluri Anjali")], set())
    assert m.status == "review" and m.student_id is None


def test_sibling_not_a_candidate():
    [m] = match_rows([R("6", "NAKKA RAVI KIRAN")], [S(13, "Nakka Ravi Teja")], set())
    assert m.status == "not_found" and m.candidates == []


def test_two_list_students_same_name():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(1, "Syed Afreen"), S(2, "AFREEN SYED")], set())
    assert m.status == "review" and {c.student_id for c in m.candidates} == {1, 2}


def test_two_file_rows_same_name():
    ms = match_rows([R("1", "SYED AFREEN", row=1), R("9", "SYED AFREEN", row=2)], [S(1, "Syed Afreen")], set())
    assert [m.status for m in ms] == ["review", "review"]


def test_same_id_across_exams_grouped():
    [m] = match_rows([R("1", "SYED AFREEN", exam=1), R("1", "SYED AFREEN", exam=2)],
                     [S(1, "Syed Afreen", "1")], set())
    assert m.status == "linked" and len(m.rows) == 2


def test_different_names_same_unlinked_id():
    [m] = match_rows([R("1", "SYED AFREEN", exam=1), R("1", "NAKKA RAVI TEJA", exam=2)],
                     [S(1, "Syed Afreen")], set())
    assert m.status == "review"


def test_duplicate_in_same_file():
    [m] = match_rows([R("1", "SYED AFREEN", row=1), R("1", "SYED AFREEN", row=2)],
                     [S(1, "Syed Afreen", "1")], set())
    assert m.status == "review"


def test_inactive_linked():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(1, "Syed Afreen", "1", active=False)], set())
    assert m.status == "review"


def test_ignored_and_not_found():
    ms = match_rows([R("5", "X Y"), R("6", "Q R")], [], {"5"})
    assert [m.status for m in ms] == ["ignored", "not_found"]


def test_linked_student_not_offered_to_new_id():
    [m] = match_rows([R("99", "SYED AFREEN")], [S(1, "Syed Afreen", "1")], set())
    assert m.status == "not_found"


def test_inactive_unlinked_student_not_offered():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(1, "Syed Afreen", active=False)], set())
    assert m.status == "not_found"


def test_one_student_never_holds_two_results():
    students = [S(1, "Syed Afreen"), S(2, "Nakka Ravi Teja", "5")]
    rows = [R("1", "SYED AFREEN"), R("5", "NAKKA RAVI TEJA"), R("8", "AFREEN SYED", row=3)]
    held = [m.student_id for m in match_rows(rows, students, set()) if m.status in ("proposed", "linked")]
    assert len(held) == len(set(held))


def test_same_name_as_a_linked_row_is_never_proposed():
    rows = [R("500", "RAHUL KUMAR", row=1), R("900", "RAHUL KUMAR", row=2)]
    students = [S(1, "Rahul Kumar", "500"), S(2, "Rahul Kumar")]
    by_id = {m.stud_id: m for m in match_rows(rows, students, set())}
    assert by_id["500"].status == "linked"
    assert by_id["900"].status == "review" and by_id["900"].student_id is None
