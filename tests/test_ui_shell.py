from streamlit.testing.v1 import AppTest

from marksapp import auth
from tests.helpers import seed_contacts


def gate_script():
    import streamlit as st

    from marksapp.ui.common import get_conn, login_gate
    if login_gate(get_conn()):
        st.write("inside")


def contacts_script():
    from marksapp.ui.common import get_conn
    from marksapp.ui.contacts_page import render
    render(get_conn())


def test_first_run_asks_for_password(app_env):
    at = AppTest.from_function(gate_script).run(timeout=30)
    assert "Set a password" in [h.value for h in at.subheader]
    at.text_input(key="new_pw").input("correct horse")
    at.text_input(key="new_pw2").input("correct horse")
    at.button(key="set_pw").click().run(timeout=30)
    assert at.session_state["logged_in"] is True
    assert "inside" in [m.value for m in at.markdown]


def test_mismatched_passwords_rejected(app_env):
    at = AppTest.from_function(gate_script).run(timeout=30)
    at.text_input(key="new_pw").input("correct horse")
    at.text_input(key="new_pw2").input("correct house")
    at.button(key="set_pw").click().run(timeout=30)
    assert at.error and not at.session_state["logged_in"]


def test_wrong_password_rejected(app_env, conn):
    auth.set_password(conn, "correct horse")
    at = AppTest.from_function(gate_script).run(timeout=30)
    assert "Log in" in [h.value for h in at.subheader]
    at.text_input(key="login_pw").input("wrong password")
    at.button(key="login_btn").click().run(timeout=30)
    assert at.error and not at.session_state["logged_in"]
    at.text_input(key="login_pw").input("correct horse")
    at.button(key="login_btn").click().run(timeout=30)
    assert at.session_state["logged_in"] is True


def test_contacts_page_renders_and_warns_siblings(app_env, conn, tmp_path):
    seed_contacts(conn, tmp_path)
    at = AppTest.from_function(contacts_script).run(timeout=30)
    assert not at.exception
    assert any("more than one child" in w.value for w in at.warning)


def test_app_file_starts_at_login(app_env):
    at = AppTest.from_file("../app.py").run(timeout=30)
    assert not at.exception
    assert "Set a password" in [h.value for h in at.subheader]


def test_contacts_page_confirms_shared_number(app_env, conn, tmp_path):
    from marksapp.contacts import unconfirmed_shared_numbers
    seed_contacts(conn, tmp_path)
    at = AppTest.from_function(contacts_script).run(timeout=30)
    at.button(key="shared_ok_+919876543205").click().run(timeout=30)
    assert not at.exception and unconfirmed_shared_numbers(conn) == []


def test_server_must_be_local_only(monkeypatch):
    from marksapp.ui import common
    for address, ok in [(None, False), ("", False), ("0.0.0.0", False), ("127.0.0.1", True), ("localhost", True)]:
        monkeypatch.setattr(common.st, "get_option", lambda key, a=address: a)
        assert common.server_is_local() is ok, address


def test_contacts_page_confirms_foreign_number(app_env, conn, tmp_path):
    from marksapp.contacts import unconfirmed_foreign_numbers, update_student
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Syed Afreen"], phone="+971501234567")
    at = AppTest.from_function(contacts_script).run(timeout=30)
    at.button(key=f"foreign_ok_{ids['Syed Afreen']}").click().run(timeout=30)
    assert not at.exception and unconfirmed_foreign_numbers(conn) == []
