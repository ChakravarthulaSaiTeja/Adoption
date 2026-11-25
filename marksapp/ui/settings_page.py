"""Settings: password, message format, exam naming rules, how WhatsApp opens."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from marksapp import auth
from marksapp.messages import MessageSettings, render_message
from marksapp.results import ExamMarks, StudentResult
from marksapp.settings import get_setting, set_setting
from marksapp.values import parse_mark

LINK_KINDS = {"wa.me": "WhatsApp link (phone or computer)", "web": "WhatsApp Web in the browser",
              "desktop": "WhatsApp desktop app"}


def _sample() -> StudentResult:
    """A made-up student, only for the preview on this page."""
    exams = [ExamMarks(exam_id=i, display_name=d, exam_type=d.split(" - ")[0], exam_number=4, mark_row_id=None,
                       maths=parse_mark(m), physics=parse_mark(p), chemistry=parse_mark(c),
                       total=parse_mark(t), total_in_file=parse_mark(t), computed_total=parse_mark(t),
                       absent_row=False, issues=[])
             for i, (d, m, p, c, t) in enumerate([("Advance Exam - 4", 41, 32, 17, 90),
                                                  ("Mains Exam - 4", 62, 17, 16, 95)])]
    return StudentResult(student_id=0, name="Sample Student", phone="+910000000000", stud_id="0",
                         exams=exams, issues=[])


def _password(conn: sqlite3.Connection) -> None:
    st.subheader("Password")
    with st.form("pw_change", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        again = st.text_input("Type the new password again", type="password")
        if st.form_submit_button("Change password"):
            if not auth.check_login(conn, current):
                st.error("Current password is wrong.")
            elif new != again:
                st.error("The new passwords do not match.")
            else:
                try:
                    auth.set_password(conn, new)
                except ValueError as e:
                    st.error(str(e))
                else:
                    st.success("Password changed.")


def _message(conn: sqlite3.Connection) -> None:
    st.subheader("Message format")
    m = get_setting(conn, "message")
    block = st.text_area("Block for each exam", m["exam_block"], height=180, key="set_block",
                         help="Use {exam}, {maths}, {physics}, {chemistry} and {total}. "
                              "Words between *stars* show in bold on WhatsApp.")
    include = st.checkbox("Start each message with the student's name", m["include_name"], key="set_inc",
                          help="Recommended when brothers or sisters share one parent's number.")
    name_line = st.text_input("Name line", m["name_line"], key="set_name", help="Use {name}.")
    ms = MessageSettings(block, m["separator"], include, name_line)
    try:
        preview = render_message(_sample(), ms)
        error = None
    except (KeyError, ValueError, IndexError) as e:
        preview, error = None, f"The format has a mistake ({e!r}). Check the {{curly brackets}}."
    if preview is not None:
        st.caption("Preview with a made-up student:")
        st.code(preview, language=None)
    if st.button("Save message format", key="set_msg_save"):
        if error:
            st.error(error)
        else:
            set_setting(conn, "message", {"exam_block": block, "separator": m["separator"],
                                          "include_name": include, "name_line": name_line})
            st.success("Saved. Messages approved earlier will need approving again.")
    elif error:
        st.error(error)


def _exam_rules(conn: sqlite3.Connection) -> None:
    st.subheader("Exam names")
    st.caption("If a file's test name contains the keyword, the exam gets that type. "
               "The order here is the order in the message.")
    rules = get_setting(conn, "exam_rules")
    edited = st.data_editor(pd.DataFrame(rules, columns=["Keyword", "Exam type"]), num_rows="dynamic",
                            hide_index=True, key="set_rules")
    if st.button("Save exam names", key="set_rules_save"):
        new_rules = [[str(k).strip().upper(), str(t).strip()] for k, t in edited.itertuples(index=False)
                     if str(k).strip() and str(t).strip() and str(k) != "None"]
        set_setting(conn, "exam_rules", new_rules)
        st.success("Saved.")


def _link_kind(conn: sqlite3.Connection) -> None:
    st.subheader("How WhatsApp opens")
    current = get_setting(conn, "link_kind")
    kind = st.radio("Open messages in", list(LINK_KINDS), index=list(LINK_KINDS).index(current),
                    format_func=LINK_KINDS.get, key="set_link")
    if kind != current:
        set_setting(conn, "link_kind", kind)
        st.success("Saved.")


def render(conn: sqlite3.Connection) -> None:
    st.title("Settings")
    _message(conn)
    st.divider()
    _exam_rules(conn)
    st.divider()
    _link_kind(conn)
    st.divider()
    _password(conn)
