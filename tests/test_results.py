from marksapp.contacts import add_student, update_student
from marksapp.results import build_results, compute_exam_marks, edit_mark, set_total_choice
from marksapp.rounds import ExamRec, MarkRowRec, confirm_links, create_round
from marksapp.values import AB, NA, Mark, parse_mark
from tests.fixtures import builders
from tests.helpers import add_file, confirm_proposed, seed_contacts, seed_round


def exam(maxes=(60, 60, 60, 180)):
    m, p, c, t = maxes
    return ExamRec(id=1, round_id=1, display_name="Advance Exam - 4", exam_type="Advance Exam",
                   exam_number=4, sort_order=0, test_name="JEE(Adv)/WTA-4", test_date=None,
                   maxes={"maths": m, "physics": p, "chemistry": c, "total": t},
                   filename="f.xlsx", file_hash="h", via_ocr=False)


def row(m, p, c, t, choice=None):
    return MarkRowRec(id=1, exam_id=1, row_no=1, stud_id="1", name_in_file="X", section=None,
                      maths=parse_mark(m), physics=parse_mark(p), chemistry=parse_mark(c),
                      total_in_file=parse_mark(t), total_choice=choice, edited=False)


def codes(issues):
    return [i.code for i in issues]


def test_normal_and_negative():
    em = compute_exam_marks(exam(), row(23, 16, -7, 32))
    assert em.total == Mark("num", 32.0) and em.issues == [] and not em.absent_row


def test_absent_row():
    em = compute_exam_marks(exam(), None)
    assert em.absent_row and em.total == AB and em.maths == AB and codes(em.issues) == ["absent"]
    assert not em.issues[0].blocking


def test_total_mismatch_blocks_until_chosen():
    em = compute_exam_marks(exam(), row(41, 32, 17, 91))
    assert [(i.code, i.blocking) for i in em.issues] == [("total_mismatch", True)]
    assert compute_exam_marks(exam(), row(41, 32, 17, 91, "file")).total == Mark("num", 91.0)
    em_sum = compute_exam_marks(exam(), row(41, 32, 17, 91, "sum"))
    assert em_sum.issues == [] and em_sum.total == Mark("num", 90.0)


def test_missing_subject_is_na_not_zero():
    em = compute_exam_marks(exam(), row(41, None, 17, 90))
    assert em.physics == NA and em.total == NA and codes(em.issues) == ["subject_missing"]
    assert not em.issues[0].blocking


def test_all_ab_in_row_is_absent():
    em = compute_exam_marks(exam(), row("AB", "AB", "AB", "AB"))
    assert em.total == AB and codes(em.issues) == ["absent"]


def test_partial_ab():
    em = compute_exam_marks(exam(), row(41, "AB", 17, 58))
    assert em.total == NA and codes(em.issues) == ["subject_absent"]


def test_out_of_range():
    assert codes(compute_exam_marks(exam(), row(75, 1, 1, 77)).issues) == ["out_of_range"]
    assert codes(compute_exam_marks(exam(), row(-61, 1, 1, -59)).issues) == ["out_of_range"]
    assert compute_exam_marks(exam(), row(75, 1, 1, 77)).issues[0].blocking


def test_total_over_max():
    em = compute_exam_marks(exam((60, 60, 60, 100)), row(50, 40, 30, 120))
    assert codes(em.issues) == ["total_over_max"] and em.issues[0].blocking


def test_build_round_one_then_linked(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    rr = build_results(conn, rid)
    assert rr.students == [] and len(rr.links_to_confirm) == 8
    confirm_proposed(conn, rid)
    rr = build_results(conn, rid)
    afreen = next(s for s in rr.students if s.name == "Syed Afreen")
    assert afreen.status == "ready" and [e.total.display() for e in afreen.exams] == ["25", "60"]
    assert [e.display_name for e in afreen.exams] == ["Advance Exam - 4", "Mains Exam - 4"]
    anjali = next(s for s in rr.students if s.name == "Kolluri Anjali")
    assert anjali.blocking and "no_phone" in codes(anjali.issues)
    assert len(rr.links_to_confirm) == 2  # the two fuzzy ones still wait for the owner


def test_linked_student_absent_from_all(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    update_student(conn, ids["Syed Afreen"], stud_id="999")
    afreen = next(s for s in build_results(conn, rid).students if s.student_id == ids["Syed Afreen"])
    assert codes(afreen.issues) == ["absent", "absent"] and afreen.status == "review" and not afreen.blocking


def test_ocr_exam_flags_every_row(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = create_round(conn, "ocr")
    add_file(conn, rid, builders.write_all_marks_files(tmp_path / "f")["xlsx"], via_ocr=True)
    confirm_proposed(conn, rid)
    students = build_results(conn, rid).students
    assert students and all("ocr" in codes(s.issues) for s in students)


def test_not_in_any_file_excludes_candidates(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    assert build_results(conn, rid).not_in_any_file == []
    extra = add_student(conn, "Extra Student", "9876543300")
    assert [r["id"] for r in build_results(conn, rid).not_in_any_file] == [extra]


def test_inactive_linked_is_blocking(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    confirm_proposed(conn, rid)
    update_student(conn, ids["Syed Afreen"], active=False)
    afreen = next(s for s in build_results(conn, rid).students if s.student_id == ids["Syed Afreen"])
    assert "inactive" in codes(afreen.issues) and afreen.blocking


def test_round_two_clean_after_short_contact_name(conn, tmp_path):
    sid = add_student(conn, "Meghana", "9876543299")
    r1 = seed_round(conn, tmp_path, mains=False)
    rr = build_results(conn, r1)
    m = next(x for x in rr.not_found + rr.links_to_confirm if x.stud_id == "100000001")
    confirm_links(conn, [(m.stud_id, sid, m.names[0])])  # owner links by hand
    r2 = seed_round(conn, tmp_path, mains=False)
    rr2 = build_results(conn, r2)
    meghana = next(s for s in rr2.students if s.student_id == sid)
    assert "match" not in codes(meghana.issues)
    assert all(x.stud_id != "100000001" for x in rr2.links_to_confirm + rr2.not_found)


def test_set_total_choice_and_edit_mark(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path, mains=False)
    confirm_proposed(conn, rid)
    s = next(x for x in build_results(conn, rid).students if x.name == "Syed Afreen")
    row_id = s.exams[0].mark_row_id
    edit_mark(conn, row_id, "total_in_file", "26")
    s = next(x for x in build_results(conn, rid).students if x.name == "Syed Afreen")
    assert "total_mismatch" in codes(s.issues) and s.blocking
    set_total_choice(conn, row_id, "sum")
    s = next(x for x in build_results(conn, rid).students if x.name == "Syed Afreen")
    assert s.status == "ready" and s.exams[0].total.display() == "25"


def test_shared_number_blocks_until_owner_confirms(conn, tmp_path):
    from marksapp.contacts import confirm_shared_number
    from tests.helpers import linked_round
    rid, rr = linked_round(conn, tmp_path)
    nakka = [s for s in rr.students if s.name.startswith("Nakka")]
    assert len(nakka) == 2 and all(s.blocking and "shared_phone" in codes(s.issues) for s in nakka)
    confirm_shared_number(conn, "+919876543205")
    nakka = [s for s in build_results(conn, rid).students if s.name.startswith("Nakka")]
    assert all(s.status == "ready" for s in nakka)
    add_student(conn, "Someone Else", "9876543205")  # a third student on the same number
    nakka = [s for s in build_results(conn, rid).students if s.name.startswith("Nakka")]
    assert all(s.blocking for s in nakka)


def test_foreign_number_blocks_until_owner_confirms(conn, tmp_path):
    from marksapp.contacts import confirm_foreign_number, unconfirmed_foreign_numbers
    from tests.helpers import linked_round
    rid, rr = linked_round(conn, tmp_path)
    afreen = next(s for s in rr.students if s.name == "Syed Afreen")
    update_student(conn, afreen.student_id, phone="+9876543210")  # typed + but forgot 91
    s = next(x for x in build_results(conn, rid).students if x.student_id == afreen.student_id)
    issue = next(i for i in s.issues if i.code == "foreign_phone")
    assert issue.blocking and "without 91" in issue.text
    assert [r["id"] for r in unconfirmed_foreign_numbers(conn)] == [afreen.student_id]
    confirm_foreign_number(conn, afreen.student_id)
    s = next(x for x in build_results(conn, rid).students if x.student_id == afreen.student_id)
    assert "foreign_phone" not in codes(s.issues)
    update_student(conn, afreen.student_id, phone="+971501234567")  # a different foreign number
    s = next(x for x in build_results(conn, rid).students if x.student_id == afreen.student_id)
    assert "foreign_phone" in codes(s.issues) and "without 91" not in s.issues[-1].text
