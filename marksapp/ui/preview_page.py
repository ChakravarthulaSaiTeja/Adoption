"""Preview & approve: see every student's exact message and approve before sending."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from marksapp.messages import message_settings, render_message
from marksapp.outbox import approve, get_outbox, skip
from marksapp.phones import pretty_phone
from marksapp.reports import STATUS_LABELS
from marksapp.results import build_results
from marksapp.rounds import LOCKING_STATES
from marksapp.ui.common import pick_round


def _status(s, rec) -> str:
    if rec is not None:
        return "Approved" if rec.status == "approved" else STATUS_LABELS.get(rec.status, rec.status)
    return "Ready" if s.status == "ready" else ("Blocked" if s.blocking else "Needs review")


def render(conn: sqlite3.Connection) -> None:
    st.title("Preview & approve")
    round_id = pick_round(conn, key="prev_round")
    if round_id is None:
        return
    rr = build_results(conn, round_id)
    if not rr.students:
        st.info("No linked students in this round yet. Confirm students on **Needs attention** first.")
        return
    ms = message_settings(conn)
    out = get_outbox(conn, round_id)
    exam_names = [em.display_name for em in rr.students[0].exams]

    rows = []
    for s in rr.students:
        row = {"Student": s.name, "WhatsApp": pretty_phone(s.phone or "") or "—"}
        for em in s.exams:
            row[em.display_name] = em.total.display()
        row["Status"] = _status(s, out.get(s.student_id))
        rows.append(row)
    df = pd.DataFrame(rows, columns=["Student", "WhatsApp", *exam_names, "Status"])
    event = st.dataframe(df, hide_index=True, on_select="rerun", selection_mode="multi-row", key="prev_table")
    selected_rows = list(getattr(getattr(event, "selection", None), "rows", []) or [])
    selected = [rr.students[i] for i in selected_rows]

    unapproved_ready = [s for s in rr.students if s.status == "ready" and s.student_id not in out]
    c1, c2, c3 = st.columns(3)
    if c1.button(f"Approve all Ready ({len(unapproved_ready)})", type="primary", key="approve_all",
                 disabled=not unapproved_ready):
        approve(conn, round_id, unapproved_ready, ms)
        st.rerun()
    if c2.button("Approve selected (Ready only)", key="approve_sel", disabled=not selected):
        approve(conn, round_id, [s for s in selected if s.status == "ready"], ms)
        st.rerun()
    if c3.button("Skip selected", key="skip_sel", disabled=not selected):
        skip(conn, round_id, [s.student_id for s in selected])
        st.rerun()
    st.caption("Students who need review are never approved in bulk: open them below.")

    st.subheader("Check one student's message")
    by_id = {s.student_id: s for s in rr.students}
    sid = st.selectbox("Student", list(by_id), key="prev_pick",
                       format_func=lambda i: f"{by_id[i].name} — {_status(by_id[i], out.get(i))}")
    s = by_id[sid]
    rec = out.get(sid)
    st.markdown(f"**To:** {pretty_phone(s.phone or '') or '⚠ no valid number'} (parent of {s.name})")
    st.code(render_message(s, ms), language=None)
    for i in s.issues:
        (st.error if i.blocking else st.warning)(i.text)
    if rec is not None and rec.status in LOCKING_STATES:
        st.info(f"Status: {STATUS_LABELS.get(rec.status, rec.status)}"
                + (f" on {rec.sent_at}" if rec.sent_at else ""))
        return
    b1, b2 = st.columns(2)
    if s.status == "ready":
        if b1.button("Approve", key="approve_one", disabled=rec is not None and rec.status == "approved"):
            approve(conn, round_id, [s], ms)
            st.rerun()
    elif b1.button("Approve after checking", key="approve_one", disabled=s.blocking,
                   help="Fix the red problems on Needs attention first." if s.blocking else None):
        approve(conn, round_id, [s], ms, allow_review=True)
        st.rerun()
    if b2.button("Skip", key="skip_one"):
        skip(conn, round_id, [sid])
        st.rerun()
