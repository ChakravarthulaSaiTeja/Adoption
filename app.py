"""Marks to Parents — run with:  streamlit run app.py"""
import streamlit as st

from marksapp.outbox import recover_interrupted
from marksapp.ui import (attention_page, contacts_page, preview_page, reports_page, round_page,
                         send_page, settings_page)
from marksapp.ui.common import get_conn, login_gate

st.set_page_config(page_title="Marks to Parents", layout="wide")
conn = get_conn()
if not st.session_state.get("recovered"):
    recover_interrupted(conn)
    st.session_state["recovered"] = True

if not login_gate(conn):
    st.stop()

pages = [
    st.Page(lambda: contacts_page.render(conn), title="Contacts", url_path="contacts", default=True),
    st.Page(lambda: round_page.render(conn), title="New round", url_path="new-round"),
    st.Page(lambda: attention_page.render(conn), title="Needs attention", url_path="needs-attention"),
    st.Page(lambda: preview_page.render(conn), title="Preview & approve", url_path="preview"),
    st.Page(lambda: send_page.render(conn), title="Send", url_path="send"),
    st.Page(lambda: reports_page.render(conn), title="Reports & history", url_path="reports"),
    st.Page(lambda: settings_page.render(conn), title="Settings", url_path="settings"),
]
st.navigation(pages).run()
