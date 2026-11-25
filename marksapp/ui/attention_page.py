"""Needs attention: confirm links, settle name differences and mark problems,
and see every row that is not going to anyone."""
from __future__ import annotations

import sqlite3

import streamlit as st

from marksapp.contacts import list_students
from marksapp.names import similarity
from marksapp.results import build_results, edit_mark, set_total_choice
from marksapp.rounds import accept_name, confirm_links, ignore_ids, unignore_id
from marksapp.ui.common import pick_round
from marksapp.ui.style import header

DECIDE, NOT_MINE = "decide", "not_mine"
DUP_HINT = ("This ID appears more than once in the same file. Correct the file, then on **New round** "
            "upload it again and tick **Replace the earlier import**.")
OTHER_HINTS = {
    "absent": "If they really were absent, approve them on Preview & approve after checking. If not, "
              "check the file: their row may be missing or their ID may be wrong.",
    "ocr": "Compare every mark with the scanned file before approving on Preview & approve.",
}
MARK_CODES = {"out_of_range", "subject_missing", "subject_absent", "total_over_max"}


def _links(conn: sqlite3.Connection, rr) -> None:
    st.subheader(f"1. Confirm students ({len(rr.links_to_confirm)})")
    if not rr.links_to_confirm:
        st.write("Nothing to confirm.")
        return
    st.caption("Every link is shown once, including the certain ones. Nothing is saved until you press "
               "**Save links**. After that, these students are recognised by their ID in every future round.")
    names = {s["id"]: s["name"] for s in list_students(conn, include_inactive=True)}
    choices: dict[str, object] = {}
    for m in rr.links_to_confirm:
        file_name = " / ".join(m.names)
        with st.container(border=True):
            if m.status == "proposed":
                choices[m.stud_id] = st.checkbox(
                    f"ID {m.stud_id} · **{file_name}** → {names.get(m.student_id)}", value=True,
                    key=f"lk_{m.stud_id}")
            else:
                st.markdown(f"ID {m.stud_id} · **{file_name}**")
                for r in m.reasons:
                    st.caption(f"⚠ {r}")
                if any("more than once" in r for r in m.reasons):
                    st.caption(DUP_HINT)
                options = [DECIDE, NOT_MINE] + [c.student_id for c in m.candidates]
                scores = {c.student_id: c.score for c in m.candidates}
                fmt = lambda o: ("Decide later" if o == DECIDE else "Not on my list" if o == NOT_MINE
                                 else f"{names.get(o)} ({scores[o]:.0f}% similar)")
                choices[m.stud_id] = st.selectbox("Who is this?", options, format_func=fmt,
                                                  key=f"lk_{m.stud_id}")
    if st.button("Save links", type="primary", key="save_links"):
        by_id = {m.stud_id: m for m in rr.links_to_confirm}
        links, ignore = [], []
        for stud_id, choice in choices.items():
            m = by_id[stud_id]
            if choice is True:
                links.append((stud_id, m.student_id, m.names[0]))
            elif choice == NOT_MINE:
                ignore.append((stud_id, m.names[0]))
            elif isinstance(choice, int) and not isinstance(choice, bool):
                links.append((stud_id, choice, m.names[0]))
        try:
            confirm_links(conn, links)
        except ValueError as e:
            st.error(f"Nothing was saved: {e}")
            return
        ignore_ids(conn, ignore)
        st.rerun()


def _name_differs(conn: sqlite3.Connection, rr, round_id: int) -> None:
    if not rr.name_flags:
        return
    by_id = {s.student_id: s for s in rr.students}
    st.subheader(f"Name in file differs from saved name ({len(rr.name_flags)})")
    for sid, flagged in rr.name_flags.items():
        s = by_id.get(sid)
        if s is None:
            continue
        with st.container(border=True):
            for n in flagged:
                st.markdown(f"**{s.name}** is linked to ID {s.stud_id}, but a file in this round says **{n}**.")
                if st.button(f"Yes, {n} is {s.name}", key=f"acc_{sid}_{n}"):
                    accept_name(conn, sid, n)
                    st.rerun()
            st.caption("If it is not the same student, unlink the ID in Contacts.")


def _marks(conn: sqlite3.Connection, rr) -> None:
    flagged = [s for s in rr.students if any(i.code in MARK_CODES | {"total_mismatch", "no_phone", "inactive", "shared_phone", "foreign_phone"}
                                             for i in s.issues)]
    st.subheader(f"2. Marks and numbers to fix ({len(flagged)})")
    if not flagged:
        st.write("Nothing to fix.")
        return
    for s in flagged:
        with st.container(border=True):
            st.markdown(f"**{s.name}**")
            for i in s.issues:
                if i.code in ("no_phone", "inactive", "shared_phone", "foreign_phone"):
                    st.error(f"{i.text} — fix it on the Contacts page.")
            for em in s.exams:
                codes = {i.code for i in em.issues}
                if "total_mismatch" in codes:
                    st.warning(next(i.text for i in em.issues if i.code == "total_mismatch"))
                    pick = st.radio("Which total is right?", ["file", "sum"], horizontal=True,
                                    key=f"tc_{em.mark_row_id}",
                                    format_func=lambda c: (f"Use file total {em.total_in_file.display()}" if c == "file"
                                                           else f"Use sum {em.computed_total.display()}"))
                    if st.button("Save total", key=f"tcs_{em.mark_row_id}"):
                        set_total_choice(conn, em.mark_row_id, pick)
                        st.rerun()
                if codes & MARK_CODES and em.mark_row_id is not None:
                    for i in em.issues:
                        if i.code in MARK_CODES:
                            st.warning(i.text)
                    cols = st.columns(4)
                    new = {
                        "maths": cols[0].text_input("Maths", em.maths.display(), key=f"em_m_{em.mark_row_id}"),
                        "physics": cols[1].text_input("Physics", em.physics.display(), key=f"em_p_{em.mark_row_id}"),
                        "chemistry": cols[2].text_input("Chemistry", em.chemistry.display(),
                                                        key=f"em_c_{em.mark_row_id}"),
                    }
                    if cols[3].button("Save marks", key=f"ems_{em.mark_row_id}"):
                        current = {"maths": em.maths, "physics": em.physics, "chemistry": em.chemistry}
                        for field, raw in new.items():
                            if raw.strip() != current[field].display():
                                edit_mark(conn, em.mark_row_id, field, raw)
                        st.rerun()
                    st.caption("Type a number, AB (absent) or NA (not available).")


def _everything_else(rr) -> None:
    """Every remaining flag, so nothing is only visible on another page."""
    items = []
    for s in rr.students:
        notes = [i for i in s.issues if i.code in OTHER_HINTS
                 or (i.code == "match" and "differs" not in i.text)]
        if notes:
            items.append((s, notes))
    if not items:
        return
    st.subheader(f"Everything else to check ({len(items)})")
    for s, notes in items:
        with st.container(border=True):
            st.markdown(f"**{s.name}**")
            seen = set()
            for i in notes:
                st.warning(i.text)
                hint = DUP_HINT if "more than once" in i.text else OTHER_HINTS.get(i.code)
                if hint and hint not in seen:
                    st.caption(hint)
                    seen.add(hint)


def _not_found(conn: sqlite3.Connection, rr) -> None:
    st.subheader(f"3. Not found on your list ({len(rr.not_found)})")
    if not rr.not_found:
        st.write("Everyone in the files was found or is waiting above.")
        return
    unlinked = [s for s in list_students(conn) if not s["stud_id"]]
    for m in rr.not_found:
        with st.container(border=True):
            st.markdown(f"ID {m.stud_id} · **{' / '.join(m.names)}** — no message will be prepared.")
            c1, c2, c3 = st.columns([2, 3, 1])
            if c1.button("Not my student", key=f"nm_{m.stud_id}"):
                ignore_ids(conn, [(m.stud_id, m.names[0])])
                st.rerun()
            if unlinked:
                names = {x["id"]: x["name"] for x in unlinked}
                pick = c2.selectbox("Or link to", list(names), index=None, placeholder="Choose a student",
                                    key=f"ln_{m.stud_id}", format_func=names.get)
                sure = False
                if pick is not None:
                    score = similarity(m.names[0], names[pick])
                    c2.caption(f"File: {m.names[0]} · Your list: {names[pick]} · {score:.0f}% similar")
                    sure = c2.checkbox(f"Yes, {m.names[0]} is {names[pick]}", key=f"lnc_{m.stud_id}")
                if c3.button("Link", key=f"lnb_{m.stud_id}", disabled=not sure):
                    try:
                        confirm_links(conn, [(m.stud_id, pick, m.names[0])])
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        st.rerun()


def _rest(conn: sqlite3.Connection, rr) -> None:
    if rr.not_in_any_file:
        with st.expander(f"On your list but not in any file ({len(rr.not_in_any_file)})"):
            st.caption("No message is prepared for these students: the app can't tell 'absent' "
                       "from 'name not recognised'. Link them above if they appear under another name.")
            st.write(", ".join(s["name"] for s in rr.not_in_any_file))
    if rr.ignored:
        with st.expander(f"Not my students ({len(rr.ignored)})"):
            for m in rr.ignored:
                c1, c2 = st.columns([4, 1])
                c1.write(f"ID {m.stud_id} · {' / '.join(m.names)}")
                if c2.button("Undo", key=f"un_{m.stud_id}"):
                    unignore_id(conn, m.stud_id)
                    st.rerun()
    if rr.unreadable:
        with st.expander(f"⚠ Rows that could not be read ({len(rr.unreadable)})", expanded=True):
            for u in rr.unreadable:
                st.write(f"{u['display_name']} · row {u['row_no']} ({u['reason']}): {u['raw_text']}")


def render(conn: sqlite3.Connection) -> None:
    header("Needs attention", "Confirm who is who, fix marks and numbers, and see every row that "
                              "won't get a message.")
    round_id = pick_round(conn, key="att_round")
    if round_id is None:
        return
    rr = build_results(conn, round_id)
    _links(conn, rr)
    _name_differs(conn, rr, round_id)
    _marks(conn, rr)
    _everything_else(rr)
    _not_found(conn, rr)
    _rest(conn, rr)
    ready = sum(s.status == "ready" for s in rr.students)
    st.info(f"{ready} of {len(rr.students)} linked students are ready. Continue on **Preview & approve**.")
