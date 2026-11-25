from streamlit.testing.v1 import AppTest

from marksapp.contacts import update_student
from marksapp.messages import message_settings
from marksapp.outbox import approve, get_outbox, mark_sent
from marksapp.settings import get_setting
from marksapp.ui.send_page import drop_stale, next_to_send
from tests.helpers import linked_round


def _at(module):
    src = f'''
import importlib
from marksapp.ui.common import get_conn
importlib.import_module("marksapp.ui.{module}").render(get_conn())
'''
    return AppTest.from_string(src)


def test_next_to_send_skips_changed(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ids = approve(conn, rid, rr.students, message_settings(conn))
    update_student(conn, ids[0], phone="9000000001")  # this approval is now stale
    assert drop_stale(conn, rid) == 1
    rec, res = next_to_send(conn, rid, None)
    assert rec.student_id != ids[0] and ids[0] not in get_outbox(conn, rid)
    assert res.student_id == rec.student_id


def test_next_to_send_respects_only(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ids = approve(conn, rid, rr.students, message_settings(conn))
    rec, _ = next_to_send(conn, rid, {ids[-1]})
    assert rec.student_id == ids[-1]


def test_next_to_send_none_when_all_sent(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    approve(conn, rid, rr.students, message_settings(conn))
    for rec in get_outbox(conn, rid).values():
        mark_sent(conn, rec.id)
    assert next_to_send(conn, rid, None) is None


def test_preview_approve_all_ready(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    at = _at("preview_page").run(timeout=30)
    assert not at.exception
    at.button(key="approve_all").click().run(timeout=30)
    assert not at.exception
    assert len(get_outbox(conn, rid)) == sum(s.status == "ready" for s in rr.students)


def test_send_page_marks_sent(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    approve(conn, rid, rr.students, message_settings(conn))
    at = _at("send_page").run(timeout=30)
    assert not at.exception
    [btn] = [b for b in at.button if (b.key or "").startswith("mark_sent_")]
    btn.click().run(timeout=30)
    assert not at.exception
    assert [r.status for r in get_outbox(conn, rid).values()].count("sent") == 1


def test_send_buttons_act_on_the_student_shown(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ready = sorted((s for s in rr.students if s.status == "ready"), key=lambda s: s.name)
    first, rest = ready[0], ready[1:]
    approve(conn, rid, rest, message_settings(conn))
    at = _at("send_page").run(timeout=30)
    shown = get_outbox(conn, rid)[rest[0].student_id]
    approve(conn, rid, [first], message_settings(conn))  # meanwhile someone approves a student who sorts first
    at.button(key=f"mark_sent_{shown.id}").click().run(timeout=30)
    out = get_outbox(conn, rid)
    assert out[rest[0].student_id].status == "sent" and out[first.student_id].status == "approved"


def test_reports_page_renders(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    at = _at("reports_page").run(timeout=30)
    assert not at.exception


def test_settings_rejects_bad_template(app_env, conn):
    before = get_setting(conn, "message")
    at = _at("settings_page").run(timeout=30)
    assert not at.exception
    at.text_area(key="set_block").input("*{exam} Marks* {maths")
    at.button(key="set_msg_save").click().run(timeout=30)
    assert at.error
    assert get_setting(conn, "message") == before


def test_settings_turns_on_name_line(app_env, conn):
    at = _at("settings_page").run(timeout=30)
    at.checkbox(key="set_inc").check()
    at.button(key="set_msg_save").click().run(timeout=30)
    assert not at.error and get_setting(conn, "message")["include_name"] is True


def test_preview_drops_approvals_after_format_change(app_env, conn, tmp_path):
    from marksapp.settings import set_setting
    rid, rr = linked_round(conn, tmp_path)
    approve(conn, rid, rr.students, message_settings(conn))
    assert get_outbox(conn, rid)
    m = get_setting(conn, "message")
    m["include_name"] = True
    set_setting(conn, "message", m)
    at = _at("preview_page").run(timeout=30)
    assert not at.exception
    assert any("approvals were cleared" in w.value for w in at.warning)
    assert get_outbox(conn, rid) == {}


def test_preview_shows_status_labels_and_bubble(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    at = _at("preview_page").run(timeout=30)
    assert not at.exception
    statuses = list(at.dataframe[0].value["Status"])
    assert "🟢 Ready" in statuses and "🔴 Blocked" in statuses
    assert any('class="wa-bubble"' in str(m.value) for m in at.markdown)


def test_settings_preview_is_a_bubble(app_env, conn):
    at = _at("settings_page").run(timeout=30)
    assert not at.exception
    assert any('class="wa-bubble"' in str(m.value) for m in at.markdown)
    titles = [h.value for h in at.subheader]
    assert titles.index("Message format") < titles.index("How WhatsApp opens") < titles.index("Exam names")
