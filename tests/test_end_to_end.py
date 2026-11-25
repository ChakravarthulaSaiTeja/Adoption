"""Whole-flow checks of the one rule that matters most: a student's marks only
ever go to that student's parent, and nothing is sent without approval."""
import pytest

from marksapp.contacts import list_students, update_student
from marksapp.messages import message_settings
from marksapp.names import title_name
from marksapp.outbox import approve, check_current, get_outbox, mark_sent
from marksapp.results import build_results
from marksapp.rounds import confirm_links, round_rows
from marksapp.settings import get_setting, set_setting
from tests.fixtures import builders
from tests.helpers import seed_contacts, seed_round


def _confirm_all(conn, rr):
    """The owner confirms proposed links and picks the top candidate for each review entry."""
    confirm_links(conn, [(m.stud_id, (m.student_id or m.candidates[0].student_id), m.names[0])
                         for m in rr.links_to_confirm if m.status == "proposed" or m.candidates])


@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
@pytest.mark.parametrize("include_name", [False, True])
def test_full_round_never_crosses_students(conn, tmp_path, fmt, include_name):
    ms0 = get_setting(conn, "message")
    ms0["include_name"] = include_name
    set_setting(conn, "message", ms0)
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path, fmt=fmt)
    _confirm_all(conn, build_results(conn, rid))
    rr = build_results(conn, rid)
    assert get_outbox(conn, rid) == {}  # processing never approves anything
    approve(conn, rid, rr.students, message_settings(conn))
    adv = {r[0]: r for r in builders.SAMPLE_ROWS}
    mains = {r[0]: r for r in builders.MAINS_ROWS}
    outbox = get_outbox(conn, rid)
    assert len(outbox) == 7  # everyone except the student with a bad number
    for sid, rec in outbox.items():
        res = next(s for s in rr.students if s.student_id == sid)
        for title, rows in (("Advance Exam - 4", adv), ("Mains Exam - 4", mains)):
            _, _, _, m, p, c, t = rows[res.stud_id]
            assert (f"*{title} Marks*\n\nMaths - {m}\nPhysics - {p}\nChemistry - {c}"
                    f"\n\n*Total Marks - {t}*") in rec.body
        others = [n for k, n, *_ in builders.SAMPLE_ROWS if k != res.stud_id]
        assert not any(title_name(n) in rec.body for n in others)
        assert (title_name(res.name) in rec.body) == include_name
        assert rec.phone == conn.execute("select phone from students where id=?", (sid,)).fetchone()[0]


def test_every_row_and_contact_accounted_for(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    for stage in ("before linking", "after linking"):
        rr = build_results(conn, rid)
        in_files = {r.stud_id for _, r in round_rows(conn, rid)}
        seen = ({s.stud_id for s in rr.students} | {m.stud_id for m in rr.links_to_confirm}
                | {m.stud_id for m in rr.not_found} | {m.stud_id for m in rr.ignored})
        assert in_files <= seen, stage
        contacts = {r["id"] for r in list_students(conn)}
        placed = ({s.student_id for s in rr.students} | {r["id"] for r in rr.not_in_any_file}
                  | {c.student_id for m in rr.links_to_confirm for c in m.candidates}
                  | {m.student_id for m in rr.links_to_confirm if m.student_id})
        assert contacts <= placed, stage
        _confirm_all(conn, rr)


def test_round_two_links_by_id(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    r1 = seed_round(conn, tmp_path)
    _confirm_all(conn, build_results(conn, r1))
    rr2 = build_results(conn, seed_round(conn, tmp_path))
    assert rr2.links_to_confirm == [] and rr2.not_found == []
    assert len(rr2.students) == 8


def test_cannot_send_unapproved(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    seed_round(conn, tmp_path)
    with pytest.raises(ValueError):
        mark_sent(conn, 99999)


def test_number_change_after_approval_blocks_send(conn, tmp_path):
    seed_contacts(conn, tmp_path)
    rid = seed_round(conn, tmp_path)
    _confirm_all(conn, build_results(conn, rid))
    rr = build_results(conn, rid)
    ms = message_settings(conn)
    approve(conn, rid, rr.students, ms)
    s = rr.students[0]
    update_student(conn, s.student_id, phone="9000000009")
    fresh = next(x for x in build_results(conn, rid).students if x.student_id == s.student_id)
    assert check_current(conn, get_outbox(conn, rid)[s.student_id], fresh, ms) is False
