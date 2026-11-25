"""Marks to Parents — run with:  streamlit run app.py"""
import streamlit as st

from marksapp.outbox import recover_interrupted
from marksapp.ui import (attention_page, contacts_page, home_page, preview_page, reports_page, round_page,
                         send_page, settings_page)
from marksapp.ui.common import get_conn, login_gate, server_is_local, sidebar_summary
from marksapp.ui.style import inject_css

st.set_page_config(page_title="Marks to Parents", page_icon="📨", layout="wide")
inject_css()
if not server_is_local():
    st.error("For privacy, this app must only be reachable from this computer. Close it and start it "
             "again from the app's own folder (where app.py is), with:  streamlit run app.py")
    st.stop()
conn = get_conn()
if not st.session_state.get("recovered"):
    recover_interrupted(conn)
    st.session_state["recovered"] = True

if not login_gate(conn):
    st.stop()

pages: dict = {}
pages.update({
    "home": st.Page(lambda: home_page.render(conn, pages), title="Home", icon=":material/home:",
                    url_path="home", default=True),
    "contacts": st.Page(lambda: contacts_page.render(conn), title="Contacts", icon=":material/contacts:",
                        url_path="contacts"),
    "round": st.Page(lambda: round_page.render(conn), title="New round", icon=":material/upload_file:",
                     url_path="new-round"),
    "attention": st.Page(lambda: attention_page.render(conn), title="Needs attention",
                         icon=":material/fact_check:", url_path="needs-attention"),
    "preview": st.Page(lambda: preview_page.render(conn), title="Preview & approve",
                       icon=":material/task_alt:", url_path="preview"),
    "send": st.Page(lambda: send_page.render(conn), title="Send", icon=":material/send:", url_path="send"),
    "reports": st.Page(lambda: reports_page.render(conn), title="Reports & history", icon=":material/bar_chart:",
                       url_path="reports"),
    "settings": st.Page(lambda: settings_page.render(conn), title="Settings", icon=":material/settings:",
                        url_path="settings"),
})
nav = st.navigation(list(pages.values()))
sidebar_summary(conn)
nav.run()
