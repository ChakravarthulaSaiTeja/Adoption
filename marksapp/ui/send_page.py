"""Send: one approved message at a time.

The owner's rule: if a WhatsApp Business API key is saved, send through the API;
otherwise use the normal method — WhatsApp opens with the message typed, the owner
presses Send there and confirms here. Both ways use the same approvals and checks.
"""
from __future__ import annotations

import sqlite3

import streamlit as st

from marksapp.messages import message_settings
from marksapp.outbox import (OutboxRec, drop_stale_approvals, get_outbox, mark_failed, mark_sent, phone_link,
                             reset_for_resend, skip)
from marksapp.phones import pretty_phone
from marksapp.results import StudentResult, build_results
from marksapp.secrets_store import load_secrets
from marksapp.sending.api import WhatsAppClient, round_shape, send_batch, template_params
from marksapp.sending.method import sending_method
from marksapp.settings import get_setting
from marksapp.ui.common import pick_round
from marksapp.ui.style import chat, chip, header, whatsapp_link_html

QUEUE_STATES = ("approved", "failed")
KIND_NAMES = {"desktop": "WhatsApp desktop app", "web": "WhatsApp Web", "wa.me": "WhatsApp link"}

drop_stale = drop_stale_approvals  # kept for older callers


def next_to_send(conn: sqlite3.Connection, round_id: int,
                 only: set[int] | None) -> tuple[OutboxRec, StudentResult] | None:
    drop_stale_approvals(conn, round_id)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    queue = [r for r in get_outbox(conn, round_id).values()
             if r.status in QUEUE_STATES and r.student_id in results
             and (only is None or r.student_id in only)]
    queue.sort(key=lambda r: results[r.student_id].name.lower())
    return (queue[0], results[queue[0].student_id]) if queue else None


def _act(conn: sqlite3.Connection, action: str, message_id: int, round_id: int) -> None:
    """Button callback, bound to the message that was on screen when the buttons were drawn."""
    try:
        if action == "sent":
            mark_sent(conn, message_id)
        elif action == "failed":
            reason = (st.session_state.get(f"fail_reason_{message_id}") or "").strip()
            mark_failed(conn, message_id, reason or "Couldn't send")
        else:
            row = conn.execute("SELECT student_id FROM messages WHERE id = ?", (message_id,)).fetchone()
            if row is not None:
                skip(conn, round_id, [row["student_id"]])
    except ValueError as e:
        st.session_state["send_error"] = str(e)


def _missing_template(conn: sqlite3.Connection, results: dict, out: dict) -> str | None:
    """The exam combination of this round, if no API template is set for it."""
    waiting = [r for r in out.values() if r.status in QUEUE_STATES and r.student_id in results]
    if not waiting:
        return None
    shape = round_shape(results[waiting[0].student_id])
    return None if (get_setting(conn, "api").get("templates") or {}).get(shape) else shape


def render(conn: sqlite3.Connection) -> None:
    header("Send", "Send each approved message to the student's parent, one at a time.")
    if "send_error" in st.session_state:
        st.error(st.session_state.pop("send_error"))
    round_id = pick_round(conn, key="send_round")
    if round_id is None:
        return
    dropped = drop_stale_approvals(conn, round_id)
    if dropped:
        st.warning(f"{dropped} messages changed since approval — approve them again on Preview & approve.")
    out = get_outbox(conn, round_id)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    queued = [r for r in out.values() if r.status in QUEUE_STATES]
    sent = [r for r in out.values() if r.status in ("sent", "accepted")]
    total = len(sent) + len(queued)
    if total:
        st.progress(len(sent) / total, text=f"{len(sent)} of {total} sent")

    kind = get_setting(conn, "link_kind")
    if sending_method(conn) == "api":
        st.markdown(chip("Sending through: WhatsApp Business API", "green"), unsafe_allow_html=True)
        use_phone = st.toggle("Send from my own WhatsApp instead", key="use_phone_instead",
                              help="For example if Meta's service is down. Approvals and checks are the same.")
        if not use_phone:
            shape = _missing_template(conn, results, out)
            if shape is None:
                _api_mode(conn, round_id, get_setting(conn, "api"), results, out)
                _already_sent(conn, sent, results)
                return
            st.info(f"No API template is set for {shape.replace('+', ' + ')}. Add it in Settings → "
                    "WhatsApp Business API, or send these from your own WhatsApp below.")
    else:
        st.markdown(chip(f"Sending through: your WhatsApp ({KIND_NAMES.get(kind, kind)})", "green"),
                    unsafe_allow_html=True)

    _phone_flow(conn, round_id, results, queued, kind)
    _already_sent(conn, sent, results)


def _phone_flow(conn: sqlite3.Connection, round_id: int, results: dict, queued: list, kind: str) -> None:
    mode = st.radio("Show", ["All approved", "Selected students", "Failed only (retry)"],
                    horizontal=True, key="send_filter", label_visibility="collapsed")
    only: set[int] | None = None
    if mode == "Selected students":
        only = set(st.multiselect("Students", [r.student_id for r in queued], key="send_only",
                                  format_func=lambda i: results[i].name if i in results else str(i)))
    elif mode == "Failed only (retry)":
        only = {r.student_id for r in queued if r.status == "failed"}

    nxt = next_to_send(conn, round_id, only)
    if nxt is None:
        st.success("Nothing left to send here. 🎉")
        return
    rec, res = nxt
    with st.container(border=True):
        st.markdown(f"#### {res.name}")
        st.caption(f"Parent's WhatsApp: {pretty_phone(rec.phone)}")
        if rec.status == "failed":
            st.warning(f"Last try didn't go through: {rec.error or 'no reason given'}")
        st.markdown(chat(rec.body), unsafe_allow_html=True)
        st.markdown(whatsapp_link_html(phone_link(rec.phone, rec.body, kind), kind), unsafe_allow_html=True)
        st.caption("WhatsApp opens with the message typed. Press Send there, then come back and click "
                   "**✅ Sent — next**. Already sent this one? Just click ✅ Sent — next.")
        c1, c2, c3 = st.columns([2, 3, 2])
        c1.button("✅ Sent — next", key=f"mark_sent_{rec.id}", type="primary",
                  on_click=_act, args=(conn, "sent", rec.id, round_id))
        with c2:
            st.text_input("Reason, if it didn't send", key=f"fail_reason_{rec.id}",
                          placeholder="e.g. number not on WhatsApp", label_visibility="collapsed")
            st.button("Couldn't send", key=f"mark_failed_{rec.id}",
                      on_click=_act, args=(conn, "failed", rec.id, round_id))
        c3.button("Skip this student", key=f"skip_this_{rec.id}",
                  on_click=_act, args=(conn, "skip", rec.id, round_id))
    if kind == "desktop":
        st.caption("First time only: your browser asks whether to open WhatsApp. Tick **Always allow**.")


def _already_sent(conn: sqlite3.Connection, sent: list, results: dict) -> None:
    if not sent:
        return
    with st.expander(f"Already sent ({len(sent)})"):
        for r in sorted(sent, key=lambda r: r.sent_at or ""):
            name = results[r.student_id].name if r.student_id in results else str(r.student_id)
            c1, c2, c3 = st.columns([4, 2, 1])
            c1.write(f"{name} · {pretty_phone(r.phone)} · {r.sent_at}"
                     + (" · via API" if r.method == "api" else ""))
            sure = c2.checkbox("Send again?", key=f"again_ok_{r.id}")
            if c3.button("Send again", key=f"again_{r.id}", disabled=not sure):
                reset_for_resend(conn, r.id)
                st.rerun()


def _run_batch(conn: sqlite3.Connection, round_id: int, ids: list[int], api: dict) -> None:
    secrets = load_secrets()
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
        st.markdown(f"**Template for {shape.replace('+', ' + ')}:** `{api['templates'][shape]}`")
        try:
            values = ", ".join(template_params(first, message_settings(conn).include_name))
            st.caption(f"Values sent for {first.name}: {values}")
        except ValueError as e:
            st.warning(str(e))
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
        st.caption("WhatsApp gave no clear answer, so these may or may not have arrived. "
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
