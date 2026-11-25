from streamlit.testing.v1 import AppTest

from marksapp.messages import message_settings
from marksapp.outbox import approve, get_outbox, mark_sent
from marksapp.ui.home_page import round_steps
from tests.helpers import linked_round


def home_script():
    from marksapp.ui.common import get_conn
    from marksapp.ui.home_page import render
    render(get_conn())


def test_steps_empty(conn):
    rnd, steps = round_steps(conn)
    assert rnd is None and [s.number for s in steps] == [1, 2, 3, 4, 5]
    assert [s.done for s in steps] == [False] * 5


def test_steps_after_linking(conn, tmp_path):
    linked_round(conn, tmp_path)
    rnd, steps = round_steps(conn)
    assert rnd is not None
    assert steps[0].summary == "8 students · 2 numbers to check" and not steps[0].done  # bad number + shared
    assert steps[1].done and steps[1].summary == "Advance Exam - 4, Mains Exam - 4"
    assert steps[2].summary == "2 students to confirm" and not steps[2].done
    assert steps[3].summary == "3 ready · 0 approved · 3 need a look"
    assert steps[4].summary == "0 of 0 sent" and not steps[4].done


def test_steps_after_sending(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ids = approve(conn, rid, rr.students, message_settings(conn))
    for sid in ids:
        mark_sent(conn, get_outbox(conn, rid)[sid].id)
    _, steps = round_steps(conn)
    assert steps[4].summary == f"{len(ids)} of {len(ids)} sent" and steps[4].done


def test_home_renders(app_env, conn, tmp_path):
    at = AppTest.from_function(home_script).run(timeout=30)
    assert not at.exception
    linked_round(conn, tmp_path)
    at = AppTest.from_function(home_script).run(timeout=30)
    assert not at.exception
    assert any("students to confirm" in str(m.value) for m in at.markdown)
