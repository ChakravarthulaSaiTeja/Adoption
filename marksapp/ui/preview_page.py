"""Preview & approve: see every student's exact message and approve before sending."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from marksapp.messages import message_settings, render_message
from marksapp.outbox import approve, drop_stale_approvals, get_outbox, skip
from marksapp.phones import pretty_phone
from marksapp.results import build_results
from marksapp.rounds import LOCKING_STATES
from marksapp.ui.common import pick_round
from marksapp.ui.style import chat, header, status_label


def _status(s, rec) -> str:
    """A key for status_label: the message's status if it has one, otherwise the student's."""
    if rec is not None:
        return rec.status
    return "ready" if s.status == "ready" else ("blocked" if s.blocking else "review")


def render(conn: sqlite3.Connection) -> None:
    header("Preview & approve", "Check each message, then approve. Nothing is sent from this page.")
    round_id = pick_round(conn, key="prev_round")
    if round_id is None:
        return
    dropped = drop_stale_approvals(conn, round_id)
    if dropped:
        st.warning(f"{dropped} approvals were cleared because marks, numbers or the message format changed. "
                   "Approve them again.")
    rr = build_results(conn, round_id)
    if not rr.students:
        st.info("No linked students in this round yet. Confirm students on **Needs attention** first.")
        return
    ms = message_settings(conn)
    out = get_outbox(conn, round_id)
    exam_names = [em.display_name for em in rr.students[0].exams]

    students = list(rr.students)  # the table's row order; selections map back through this list
    rows = []
    for s in students:
        row = {"Student": s.name, "WhatsApp": pretty_phone(s.phone or "") or "—"}
        for em in s.exams:
            row[em.display_name] = em.total.display()
        row["Status"] = status_label(_status(s, out.get(s.student_id)))
        rows.append(row)
    df = pd.DataFrame(rows, columns=["Student", "WhatsApp", *exam_names, "Status"])
    event = st.dataframe(df, hide_index=True, on_select="rerun", selection_mode="multi-row",
                         key=f"prev_table_{round_id}")
    picked = getattr(getattr(event, "selection", None), "rows", []) or []
    selected = [students[i] for i in picked if 0 <= i < len(students)]

    unapproved_ready = [s for s in students if s.status == "ready" and s.student_id not in out]
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
    st.caption("Students who need a look are never approved in bulk: open them below.")

    st.subheader("Check one student's message")
    by_id = {s.student_id: s for s in students}
    sid = st.selectbox("Student", list(by_id), key=f"prev_pick_{round_id}",
                       format_func=lambda i: f"{by_id[i].name} — {status_label(_status(by_id[i], out.get(i)))}")
    s = by_id[sid]
    rec = out.get(sid)
    left, right = st.columns([3, 2], gap="large")
    left.markdown(chat(render_message(s, ms)), unsafe_allow_html=True)
    with right:
        st.markdown(f"**To:** {pretty_phone(s.phone or '') or '⚠ no valid number'}")
        st.caption(f"Parent of {s.name}")
        for i in s.issues:
            (st.error if i.blocking else st.warning)(i.text)
        if rec is not None and rec.status in LOCKING_STATES:
            st.info(f"Status: {status_label(rec.status)}" + (f" on {rec.sent_at}" if rec.sent_at else ""))
            return
        b1, b2 = st.columns(2)
        if s.status == "ready":
            if b1.button("Approve", key="approve_one", type="primary",
                         disabled=rec is not None and rec.status == "approved"):
                approve(conn, round_id, [s], ms)
                st.rerun()
        elif b1.button("Approve after checking", key="approve_one", disabled=s.blocking,
                       help="Fix the red problems on Needs attention first." if s.blocking else None):
            approve(conn, round_id, [s], ms, allow_review=True)
            st.rerun()
        if b2.button("Skip", key="skip_one"):
            skip(conn, round_id, [sid])
            st.rerun()
