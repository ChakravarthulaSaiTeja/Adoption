"""Sending through the official WhatsApp Business Cloud API (Meta).

Messages a business starts must use a template Meta has approved. Template
variables cannot hold line breaks, so the layout lives in the template and only
the numbers (and optionally the name) are filled in. See docs/whatsapp-api-setup.md.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass

import requests

from marksapp.messages import message_settings
from marksapp.names import title_name
from marksapp.outbox import (check_current, get_outbox, mark_accepted, mark_failed, mark_sending,
                             mark_unknown)
from marksapp.results import StudentResult, build_results
from marksapp.settings import get_setting

GRAPH_URL = "https://graph.facebook.com"
STOP_CODES = {0, 4, 190, 80007, 130429, 131048, 131056}  # auth problems and rate limits


class ApiError(Exception):
    def __init__(self, code: int | None, message: str, stop: bool):
        super().__init__(message)
        self.code, self.message, self.stop = code, message, stop


def validate_param(p: str) -> None:
    if not p or not p.strip():
        raise ValueError("Empty value")
    if "\n" in p or "\t" in p or re.search(r" {5,}", p):
        raise ValueError(f"WhatsApp does not allow line breaks, tabs or long spaces in a value: {p!r}")


class WhatsAppClient:
    def __init__(self, phone_number_id: str, token: str, api_version: str = "v24.0",
                 session: requests.Session | None = None, timeout: float = 30.0):
        self.phone_number_id, self.token, self.api_version = phone_number_id, token, api_version
        self.session = session or requests.Session()
        self.timeout = timeout

    def send_template(self, to_e164: str, template: str, language: str, params: list[str]) -> str:
        for p in params:
            validate_param(p)
        body = {
            "messaging_product": "whatsapp",
            "to": to_e164.lstrip("+"),
            "type": "template",
            "template": {"name": template, "language": {"code": language},
                         "components": [{"type": "body",
                                         "parameters": [{"type": "text", "text": p} for p in params]}]},
        }
        resp = self.session.post(f"{GRAPH_URL}/{self.api_version}/{self.phone_number_id}/messages",
                                 json=body, headers={"Authorization": f"Bearer {self.token}"},
                                 timeout=self.timeout)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error") or {}
            code = err.get("code")
            message = err.get("message") or f"HTTP {resp.status_code}"
            raise ApiError(code, message, resp.status_code == 401 or code in STOP_CODES)
        return data["messages"][0]["id"]


def round_shape(result: StudentResult) -> str:
    return "+".join(e.exam_type for e in result.exams)


def template_params(result: StudentResult, include_name: bool) -> list[str]:
    params = [title_name(result.name)] if include_name else []
    for e in result.exams:
        if e.exam_number is None:
            raise ValueError(f"{e.display_name} has no exam number, which the API template needs")
        params += [str(e.exam_number),
                   e.maths.display(), e.physics.display(), e.chemistry.display(), e.total.display()]
    return params


@dataclass
class BatchOutcome:
    accepted: int = 0
    failed: int = 0
    unknown: int = 0
    skipped_changed: int = 0
    stopped_reason: str | None = None


def send_batch(conn: sqlite3.Connection, round_id: int, student_ids: list[int], client: WhatsAppClient,
               *, sleep=time.sleep) -> BatchOutcome:
    api = get_setting(conn, "api")
    ms = message_settings(conn)
    results = {s.student_id: s for s in build_results(conn, round_id).students}
    out = get_outbox(conn, round_id)
    eligible = [out[sid] for sid in student_ids if sid in out and out[sid].status in ("approved", "failed")]

    templates = api.get("templates") or {}
    missing = {round_shape(results[r.student_id]) for r in eligible
               if r.student_id in results and not templates.get(round_shape(results[r.student_id]))}
    if missing:
        raise ValueError("No template set for: " + ", ".join(sorted(missing)))

    outcome = BatchOutcome()
    sent_any = False
    for rec in eligible:
        res = results.get(rec.student_id)
        if not check_current(conn, rec, res, ms):
            outcome.skipped_changed += 1
            continue
        try:
            params = template_params(res, ms.include_name)
            for p in params:
                validate_param(p)
        except ValueError as e:
            mark_failed(conn, rec.id, f"Can't send: {e}")
            outcome.failed += 1
            continue
        if sent_any:
            sleep(float(api.get("pause_seconds", 2.0)))
        sent_any = True
        mark_sending(conn, rec.id)
        try:
            wamid = client.send_template(rec.phone, templates[round_shape(res)], api.get("language", "en"), params)
        except ApiError as e:
            mark_failed(conn, rec.id, f"{e.message} (code {e.code})")
            outcome.failed += 1
            if e.stop:
                outcome.stopped_reason = e.message
                break
            continue
        except (requests.Timeout, requests.ConnectionError):
            # The request may have reached WhatsApp: never retry automatically.
            mark_unknown(conn, rec.id, "No clear answer from WhatsApp — check before sending again")
            outcome.unknown += 1
            continue
        except requests.RequestException as e:
            mark_failed(conn, rec.id, f"Network error: {e}")
            outcome.failed += 1
            continue
        mark_accepted(conn, rec.id, wamid)
        outcome.accepted += 1
    return outcome
