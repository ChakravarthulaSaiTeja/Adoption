"""Build the exact WhatsApp text for one student, and its fingerprint."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from marksapp.names import title_name
from marksapp.results import StudentResult
from marksapp.settings import get_setting


@dataclass(frozen=True)
class MessageSettings:
    exam_block: str
    separator: str
    include_name: bool
    name_line: str


def message_settings(conn: sqlite3.Connection) -> MessageSettings:
    m = get_setting(conn, "message")
    return MessageSettings(m["exam_block"], m["separator"], bool(m["include_name"]), m["name_line"])


def render_message(result: StudentResult, ms: MessageSettings) -> str:
    """Only this one student's values ever go into the body."""
    parts = []
    if ms.include_name:
        parts.append(ms.name_line.format(name=title_name(result.name)))
    for em in result.exams:
        parts.append(ms.exam_block.format(
            exam=em.display_name, maths=em.maths.display(), physics=em.physics.display(),
            chemistry=em.chemistry.display(), total=em.total.display()))
    return ms.separator.join(parts)


def content_hash(phone: str, body: str) -> str:
    return hashlib.sha256(f"{phone}\n{body}".encode()).hexdigest()
