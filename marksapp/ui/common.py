"""Shared Streamlit helpers: one database connection per session, the login gate,
and the round picker."""
from __future__ import annotations

import sqlite3

import streamlit as st

from marksapp import auth
from marksapp.db import connect
from marksapp.rounds import list_rounds


def get_conn() -> sqlite3.Connection:
    if "conn" not in st.session_state:
        st.session_state["conn"] = connect(check_same_thread=False)
    return st.session_state["conn"]


def login_gate(conn: sqlite3.Connection) -> bool:
    if st.session_state.get("logged_in"):
        return True
    st.session_state.setdefault("logged_in", False)
    if not auth.password_is_set(conn):
        st.subheader("Set a password")
        st.caption("This password protects your students' marks and parents' numbers. "
                   "It is needed every time the app is opened.")
        pw = st.text_input("New password (at least 8 characters)", type="password", key="new_pw")
        pw2 = st.text_input("Type it again", type="password", key="new_pw2")
        if st.button("Set password", key="set_pw"):
            if pw != pw2:
                st.error("The two passwords do not match.")
            else:
                try:
                    auth.set_password(conn, pw)
                except ValueError as e:
                    st.error(str(e))
                else:
                    st.session_state["logged_in"] = True
                    return True
        return False
    st.subheader("Log in")
    pw = st.text_input("Password", type="password", key="login_pw")
    if st.button("Log in", key="login_btn"):
        if auth.check_login(conn, pw):
            st.session_state["logged_in"] = True
            return True
        st.error("Wrong password.")
    return False


def pick_round(conn: sqlite3.Connection, key: str) -> int | None:
    rounds = list_rounds(conn)
    if not rounds:
        st.info("No rounds yet. Start one on the **New round** page.")
        return None
    labels = {r["id"]: f"{r['label']} (started {r['created_at'][:10]})" for r in rounds}
    return st.selectbox("Round", list(labels), format_func=labels.get, key=key)
