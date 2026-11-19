import pytest

from marksapp.contacts import update_student
from marksapp.messages import message_settings
from marksapp.outbox import (approve, check_current, get_outbox, mark_accepted, mark_failed, mark_sending,
                             mark_sent, mark_unknown, phone_link, recover_interrupted, reset_for_resend, skip)
from marksapp.results import build_results
from tests.helpers import linked_round


def _ready(rr):
    return [s for s in rr.students if s.status == "ready"]


def test_approve_only_ready(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ms = message_settings(conn)
    approved = approve(conn, rid, rr.students, ms)
    assert set(approved) == {s.student_id for s in _ready(rr)} and approved
    blocked = [s for s in rr.students if s.blocking]
    assert blocked and approve(conn, rid, blocked, ms, allow_review=True) == []
    rec = get_outbox(conn, rid)[approved[0]]
    assert rec.status == "approved" and rec.body.startswith("*Advance Exam - 4 Marks*")


def test_change_after_approval_clears(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ms = message_settings(conn)
    s = _ready(rr)[0]
    approve(conn, rid, [s], ms)
    rec = get_outbox(conn, rid)[s.student_id]
    assert check_current(conn, rec, s, ms) is True
    update_student(conn, s.student_id, phone="9000000001")
    fresh = next(x for x in build_results(conn, rid).students if x.student_id == s.student_id)
    assert check_current(conn, rec, fresh, ms) is False
    assert s.student_id not in get_outbox(conn, rid)


def test_mark_sent_twice_raises(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    [sid] = approve(conn, rid, _ready(rr)[:1], message_settings(conn))
    rec = get_outbox(conn, rid)[sid]
    mark_sent(conn, rec.id)
    after = get_outbox(conn, rid)[sid]
    assert after.status == "sent" and after.sent_at and after.method == "phone" and after.attempts == 1
    with pytest.raises(ValueError):
        mark_sent(conn, rec.id)


def test_resend_requires_reset(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    [sid] = approve(conn, rid, _ready(rr)[:1], message_settings(conn))
    mid = get_outbox(conn, rid)[sid].id
    mark_sent(conn, mid)
    reset_for_resend(conn, mid)
    assert get_outbox(conn, rid)[sid].status == "approved"
    mark_sent(conn, mid)
    assert get_outbox(conn, rid)[sid].attempts == 2


def test_failed_then_retry(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    [sid] = approve(conn, rid, _ready(rr)[:1], message_settings(conn))
    mid = get_outbox(conn, rid)[sid].id
    mark_failed(conn, mid, "Number not on WhatsApp")
    assert get_outbox(conn, rid)[sid].error == "Number not on WhatsApp"
    mark_sent(conn, mid)
    assert get_outbox(conn, rid)[sid].status == "sent"


def test_api_path_and_recover_interrupted(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    a, b = approve(conn, rid, _ready(rr)[:2], message_settings(conn))
    out = get_outbox(conn, rid)
    mark_sending(conn, out[a].id)
    mark_accepted(conn, out[a].id, "wamid.X")
    mark_sending(conn, out[b].id)
    assert recover_interrupted(conn) == 1
    out = get_outbox(conn, rid)
    assert (out[a].status, out[a].api_message_id, out[a].attempts) == ("accepted", "wamid.X", 1)
    assert out[b].status == "unknown"
    with pytest.raises(ValueError):
        mark_sending(conn, out[b].id)  # never resent automatically


def test_mark_unknown_from_sending(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    [sid] = approve(conn, rid, _ready(rr)[:1], message_settings(conn))
    mid = get_outbox(conn, rid)[sid].id
    mark_sending(conn, mid)
    mark_unknown(conn, mid, "Timed out")
    assert get_outbox(conn, rid)[sid].status == "unknown"


def test_approve_never_touches_sent(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ms = message_settings(conn)
    ids = approve(conn, rid, rr.students, ms)
    mid = get_outbox(conn, rid)[ids[0]].id
    mark_sent(conn, mid)
    again = approve(conn, rid, rr.students, ms)
    assert ids[0] not in again and get_outbox(conn, rid)[ids[0]].status == "sent"


def test_skip(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    s = _ready(rr)[0]
    skip(conn, rid, [s.student_id])
    assert get_outbox(conn, rid)[s.student_id].status == "skipped"
    approve(conn, rid, [s], message_settings(conn))
    assert get_outbox(conn, rid)[s.student_id].status == "approved"


def test_phone_link():
    assert phone_link("+919876543201", "*A*\nB", "wa.me") == "https://wa.me/919876543201?text=%2AA%2A%0AB"
    assert phone_link("+919876543201", "x", "web") == "https://web.whatsapp.com/send?phone=919876543201&text=x"
    assert phone_link("+919876543201", "x", "desktop") == "whatsapp://send?phone=919876543201&text=x"
