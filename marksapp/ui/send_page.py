"""Send: one approved message at a time, opened in WhatsApp; the owner presses Send."""
from __future__ import annotations

import sqlite3

import streamlit as st

from marksapp.messages import message_settings
from marksapp.outbox import (OutboxRec, check_current, get_outbox, mark_failed, mark_sent, phone_link,
                             reset_for_resend, skip)
from marksapp.phones import pretty_phone
from marksapp.results import StudentResult, build_results
from marksapp.secrets_store import load_secrets
from marksapp.sending.api import WhatsAppClient, round_shape, send_batch, template_params
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

    api = get_setting(conn, "api")
    if api.get("enabled"):
        how = st.radio("How to send", ["From my phone", "Through WhatsApp API"], horizontal=True, key="send_mode")
        if how == "Through WhatsApp API":
            _api_mode(conn, round_id, api, results, out)
            return

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


def _run_batch(conn: sqlite3.Connection, round_id: int, ids: list[int], api: dict) -> None:
    secrets = load_secrets()
    if not secrets.get("phone_number_id") or not secrets.get("access_token"):
        st.error("Add the Phone Number ID and access token in Settings first.")
        return
    client = WhatsAppClient(secrets["phone_number_id"], secrets["access_token"], api.get("api_version", "v24.0"))
    try:
        with st.spinner(f"Sending {len(ids)} messages…"):
            o = send_batch(conn, round_id, ids, client)
    except ValueError as e:
        st.session_state["api_outcome"] = ("error", str(e))
    else:
        text = (f"Accepted by WhatsApp: {o.accepted} · Failed: {o.failed} · Unknown: {o.unknown}"
                + (f" · Changed since approval (not sent): {o.skipped_changed}" if o.skipped_changed else ""))
        if o.stopped_reason:
            text += f". Stopped early: {o.stopped_reason}"
        st.session_state["api_outcome"] = ("error" if o.stopped_reason else "success", text)
    st.rerun()


def _api_mode(conn: sqlite3.Connection, round_id: int, api: dict, results: dict, out: dict) -> None:
    approved = [r for r in out.values() if r.status == "approved" and r.student_id in results]
    failed = [r for r in out.values() if r.status == "failed" and r.student_id in results]
    unknown = [r for r in out.values() if r.status == "unknown"]
    kind, text = st.session_state.pop("api_outcome", (None, None))
    if kind:
        (st.error if kind == "error" else st.success)(text)

    if approved:
        first = results[approved[0].student_id]
        shape = round_shape(first)
        template = (api.get("templates") or {}).get(shape)
        st.markdown(f"**Template for {shape.replace('+', ' + ')}:** "
                    + (f"`{template}`" if template else "⚠ none set — add it in Settings"))
        st.caption(f"Values sent for {first.name}: " + ", ".join(template_params(first, message_settings(conn).include_name)))
    c1, c2 = st.columns(2)
    if c1.button(f"Send all approved ({len(approved)})", type="primary", key="api_send_all", disabled=not approved):
        _run_batch(conn, round_id, [r.student_id for r in approved], api)
    if c2.button(f"Retry failed ({len(failed)})", key="api_retry", disabled=not failed):
        _run_batch(conn, round_id, [r.student_id for r in failed], api)
    chosen = st.multiselect("Or send only these students", [r.student_id for r in approved + failed],
                            format_func=lambda i: results[i].name, key="api_sel")
    if st.button("Send selected", key="api_send_sel", disabled=not chosen):
        _run_batch(conn, round_id, chosen, api)

    if unknown:
        st.subheader(f"Unknown — check ({len(unknown)})")
        st.caption("WhatsApp did not answer in time, so these may or may not have arrived. "
                   "Check the parent's chat in WhatsApp Business before sending again.")
        for r in unknown:
            name = results[r.student_id].name if r.student_id in results else str(r.student_id)
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.write(f"{name} · {pretty_phone(r.phone)}")
            if c2.button("It arrived", key=f"arr_{r.id}"):
                mark_sent(conn, r.id, method="api")
                st.rerun()
            if c3.button("Send again", key=f"res_{r.id}"):
                reset_for_resend(conn, r.id)
                st.rerun()
