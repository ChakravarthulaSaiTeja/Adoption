"""Home: where the latest round stands, as five steps, and what to do next."""
from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass

import streamlit as st

from marksapp.contacts import list_students, unconfirmed_shared_numbers
from marksapp.outbox import get_outbox
from marksapp.results import build_results
from marksapp.rounds import list_exams, list_rounds
from marksapp.ui.style import header

SENT = ("sent", "accepted")


@dataclass
class Step:
    number: int
    title: str
    summary: str
    done: bool
    page: str  # key of the page this step opens


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def round_steps(conn: sqlite3.Connection) -> tuple[sqlite3.Row | None, list[Step]]:
    students = list_students(conn)
    to_check = sum(1 for s in students if not s["phone"]) + len(unconfirmed_shared_numbers(conn))
    contacts = Step(1, "Contacts", _plural(len(students), "student")
                    + (f" · {_plural(to_check, 'number')} to check" if to_check else ""),
                    bool(students) and to_check == 0, "contacts")
    rounds = list_rounds(conn)
    if not rounds:
        rest = [Step(2, "Files", "No round yet", False, "round"),
                Step(3, "Confirm students", "No round yet", False, "attention"),
                Step(4, "Approve", "No round yet", False, "preview"),
                Step(5, "Send", "No round yet", False, "send")]
        return None, [contacts, *rest]

    rnd = rounds[0]
    exams = list_exams(conn, rnd["id"])
    files = Step(2, "Files", ", ".join(e.display_name for e in exams) or "No files yet", bool(exams), "round")
    rr = build_results(conn, rnd["id"]) if exams else None
    to_confirm = len(rr.links_to_confirm) if rr else 0
    confirm = Step(3, "Confirm students",
                   f"{_plural(to_confirm, 'student')} to confirm" if to_confirm else
                   ("All students confirmed" if exams else "Add files first"),
                   bool(exams) and to_confirm == 0, "attention")
    out = get_outbox(conn, rnd["id"])
    students_r = rr.students if rr else []
    ready = sum(1 for s in students_r if s.status == "ready" and s.student_id not in out)
    look = sum(1 for s in students_r if s.status == "review" and s.student_id not in out)
    approved = sum(1 for r in out.values() if r.status == "approved")
    sent = sum(1 for r in out.values() if r.status in SENT)
    approve = Step(4, "Approve", f"{ready} ready · {approved} approved · {look} need a look",
                   ready == 0 and look == 0 and approved + sent > 0, "preview")
    total = sum(1 for r in out.values() if r.status in ("approved", "failed", "sending", "unknown", *SENT))
    send = Step(5, "Send", f"{sent} of {total} sent", total > 0 and sent == total, "send")
    return rnd, [contacts, files, confirm, approve, send]


def render(conn: sqlite3.Connection, pages: dict | None = None) -> None:
    header("Home", "Where this round stands, and what to do next.")
    rnd, steps = round_steps(conn)
    if rnd is None:
        st.info("No round yet. Every two weeks: check **Contacts**, add the marks files on **New round**, "
                "confirm students, approve the messages, then send them.")
    else:
        st.markdown(f"**{html.escape(rnd['label'])}**")
    next_step = next((s for s in steps if not s.done), None)
    for s in steps:
        state = "done" if s.done else ("next" if s is next_step else "")
        mark = "✓" if s.done else str(s.number)
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(
            f'<div class="step {state}"><div class="step-num">{mark}</div><div>'
            f'<div class="step-title">{html.escape(s.title)}</div>'
            f'<div class="step-summary">{html.escape(s.summary)}</div></div></div>',
            unsafe_allow_html=True)
        if pages and s.page in pages:
            c2.page_link(pages[s.page], label="Open", icon=":material/arrow_forward:")
    if next_step is None and rnd is not None:
        st.success("This round is finished: every approved message has been sent. 🎉")
