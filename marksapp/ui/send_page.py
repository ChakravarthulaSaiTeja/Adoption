"""Send: one approved message at a time, opened in WhatsApp; the owner presses Send."""
from __future__ import annotations

import sqlite3

import streamlit as st

from marksapp.messages import message_settings
from marksapp.outbox import (OutboxRec, check_current, get_outbox, mark_failed, mark_sent, phone_link,
                             reset_for_resend, skip)
from marksapp.phones import pretty_phone
from marksapp.results import StudentResult, build_results
from marksapp.settings import get_setting
from marksapp.ui.common import pick_round

QUEUE_STATES = ("approved", "failed")


def drop_stale(conn: sqlite3.Connection, round_id: int) -> int:
    """Drop every approval whose number or text no longer matches. Returns how many."""
    ms = message_settings(conn)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    dropped = 0
    for rec in get_outbox(conn, round_id).values():
        if rec.status in QUEUE_STATES and not check_current(conn, rec, results.get(rec.student_id), ms):
            dropped += 1
    return dropped


def next_to_send(conn: sqlite3.Connection, round_id: int,
                 only: set[int] | None) -> tuple[OutboxRec, StudentResult] | None:
    drop_stale(conn, round_id)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    queue = [r for r in get_outbox(conn, round_id).values()
             if r.status in QUEUE_STATES and r.student_id in results
             and (only is None or r.student_id in only)]
    queue.sort(key=lambda r: results[r.student_id].name.lower())
    return (queue[0], results[queue[0].student_id]) if queue else None


def render(conn: sqlite3.Connection) -> None:
    st.title("Send")
    round_id = pick_round(conn, key="send_round")
    if round_id is None:
        return
    dropped = drop_stale(conn, round_id)
    if dropped:
        st.warning(f"{dropped} messages changed since approval — re-approve them on Preview.")
    out = get_outbox(conn, round_id)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    queued = [r for r in out.values() if r.status in QUEUE_STATES]
    sent = [r for r in out.values() if r.status in ("sent", "accepted")]
    st.write(f"**{len(sent)} of {len(sent) + len(queued)} sent.**")

    mode = st.radio("Send", ["All approved", "Selected students", "Failed only (retry)"],
                    horizontal=True, key="send_filter")
    only: set[int] | None = None
    if mode == "Selected students":
        options = [r.student_id for r in queued]
        only = set(st.multiselect("Students", options, key="send_only",
                                  format_func=lambda i: results[i].name if i in results else str(i)))
    elif mode == "Failed only (retry)":
        only = {r.student_id for r in queued if r.status == "failed"}

    nxt = next_to_send(conn, round_id, only)
    if nxt is None:
        st.success("Nothing left to send here.")
    else:
        rec, res = nxt
        with st.container(border=True):
            st.markdown(f"### {res.name}")
            st.markdown(f"**Parent's WhatsApp:** {pretty_phone(rec.phone)}")
            if rec.status == "failed":
                st.warning(f"Last try failed: {rec.error or 'no reason given'}")
            st.code(rec.body, language=None)
            st.link_button("Open in WhatsApp", phone_link(rec.phone, rec.body, get_setting(conn, "link_kind")),
                           type="primary")
            st.caption("WhatsApp opens with the message typed. Press Send there, then come back and confirm.")
            c1, c2, c3 = st.columns(3)
            if c1.button("✅ Sent", key="mark_sent"):
                mark_sent(conn, rec.id)
                st.rerun()
            reason = c2.text_input("Reason (if it didn't send)", key="fail_reason")
            if c2.button("Couldn't send", key="mark_failed"):
                mark_failed(conn, rec.id, reason.strip() or "Couldn't send")
                st.rerun()
            if c3.button("Skip this student", key="skip_this"):
                skip(conn, round_id, [rec.student_id])
                st.rerun()

    if sent:
        with st.expander(f"Already sent ({len(sent)})"):
            for r in sorted(sent, key=lambda r: r.sent_at or ""):
                name = results[r.student_id].name if r.student_id in results else str(r.student_id)
                c1, c2, c3 = st.columns([4, 2, 1])
                c1.write(f"{name} · {pretty_phone(r.phone)} · sent on {r.sent_at}")
                sure = c2.checkbox("Send again?", key=f"again_ok_{r.id}")
                if c3.button("Send again", key=f"again_{r.id}", disabled=not sure):
                    reset_for_resend(conn, r.id)
                    st.rerun()
