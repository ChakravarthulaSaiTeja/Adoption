"""Reports & history: delivery report per round, each student's history, audit log."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from marksapp import audit
from marksapp.contacts import list_students
from marksapp.reports import message_log, report_xlsx, round_counts, round_report, student_history
from marksapp.ui.common import pick_round
from marksapp.ui.style import header


def render(conn: sqlite3.Connection) -> None:
    header("Reports & history", "What was sent this round, each student's marks over time, and the activity log.")
    st.subheader("Delivery report")
    round_id = pick_round(conn, key="rep_round")
    if round_id is not None:
        counts = round_counts(conn, round_id)
        cols = st.columns(len(counts))
        for col, (label, n) in zip(cols, counts.items()):
            col.metric(label, n)
        df = round_report(conn, round_id)
        st.dataframe(df, hide_index=True)
        st.download_button("Download Excel", report_xlsx(df), file_name=f"delivery-report-round-{round_id}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="rep_download")

    st.subheader("Student history")
    students = list_students(conn, include_inactive=True)
    if students:
        by_id = {s["id"]: s for s in students}
        sid = st.selectbox("Student", list(by_id), format_func=lambda i: by_id[i]["name"], key="hist_pick")
        st.markdown("**Marks**")
        st.dataframe(student_history(conn, sid), hide_index=True)
        st.markdown("**Messages**")
        st.dataframe(message_log(conn, sid), hide_index=True)
    else:
        st.write("No students yet.")

    with st.expander("Activity log (latest 200)"):
        st.dataframe(pd.DataFrame([{"Time": r["ts"], "Action": r["action"], "Details": r["details"]}
                                   for r in audit.recent(conn)], columns=["Time", "Action", "Details"]),
                     hide_index=True)
