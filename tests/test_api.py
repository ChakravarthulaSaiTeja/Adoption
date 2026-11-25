import os

import pytest
import requests

from marksapp.messages import message_settings
from marksapp.outbox import approve, get_outbox
from marksapp.secrets_store import load_secrets, save_secrets, secrets_path
from marksapp.sending.api import WhatsAppClient, send_batch, template_params, validate_param
from marksapp.settings import get_setting, set_setting
from tests.helpers import linked_round, make_result


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


OK = lambda i: FakeResponse(200, {"messages": [{"id": f"wamid.{i}"}]})
ERR = lambda status, code, msg: FakeResponse(status, {"error": {"code": code, "message": msg}})


def _setup(conn, tmp_path, n=2, templates=None):
    api = get_setting(conn, "api")
    api["templates"] = {"Advance Exam+Mains Exam": "marks_adv_mains"} if templates is None else templates
    set_setting(conn, "api", api)
    rid, rr = linked_round(conn, tmp_path)
    ids = approve(conn, rid, [s for s in rr.students if s.status == "ready"][:n], message_settings(conn))
    return rid, ids


def test_request_shape():
    fake = FakeSession(OK(1))
    client = WhatsAppClient("PNID", "TOKEN", session=fake)
    assert client.send_template("+919876543201", "marks_adv_mains", "en",
                                template_params(make_result(), False)) == "wamid.1"
    call = fake.calls[0]
    assert "/v24.0/PNID/messages" in call["url"] and call["headers"]["Authorization"] == "Bearer TOKEN"
    body = call["json"]
    assert body["to"] == "919876543201" and body["type"] == "template"
    assert body["template"]["name"] == "marks_adv_mains" and body["template"]["language"] == {"code": "en"}
    texts = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert texts == ["4", "41", "32", "17", "90", "4", "62", "17", "16", "95"]


def test_template_params_with_name():
    assert template_params(make_result(), True)[0] == "Pallapu Meghana Sri"


def test_success_marks_accepted(conn, tmp_path):
    rid, ids = _setup(conn, tmp_path)
    fake, sleeps = FakeSession(OK(1), OK(2)), []
    outcome = send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=sleeps.append)
    assert (outcome.accepted, outcome.failed, outcome.stopped_reason) == (2, 0, None)
    rec = get_outbox(conn, rid)[ids[0]]
    assert rec.status == "accepted" and rec.api_message_id.startswith("wamid.") and rec.attempts == 1
    assert sleeps == [2.0]


def test_undeliverable_continues(conn, tmp_path):
    rid, ids = _setup(conn, tmp_path)
    fake = FakeSession(ERR(400, 131026, "Message undeliverable"), OK(2))
    outcome = send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=lambda s: None)
    out = get_outbox(conn, rid)
    assert (outcome.accepted, outcome.failed) == (1, 1)
    assert out[ids[0]].status == "failed" and "undeliverable" in out[ids[0]].error
    assert out[ids[0]].attempts == 1


def test_auth_error_stops(conn, tmp_path):
    rid, ids = _setup(conn, tmp_path)
    fake = FakeSession(ERR(401, 190, "Invalid access token"))
    outcome = send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=lambda s: None)
    assert outcome.stopped_reason == "Invalid access token" and len(fake.calls) == 1
    assert get_outbox(conn, rid)[ids[1]].status == "approved"


def test_timeout_is_unknown_and_not_resent(conn, tmp_path):
    rid, ids = _setup(conn, tmp_path, n=1)
    fake = FakeSession(requests.Timeout("slow"))
    outcome = send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=lambda s: None)
    assert outcome.unknown == 1 and get_outbox(conn, rid)[ids[0]].status == "unknown"
    send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=lambda s: None)
    assert len(fake.calls) == 1


def test_missing_template_raises_before_any_call(conn, tmp_path):
    rid, ids = _setup(conn, tmp_path, templates={})
    fake = FakeSession()
    with pytest.raises(ValueError, match="No template set for: Advance Exam\\+Mains Exam"):
        send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=lambda s: None)
    assert fake.calls == [] and get_outbox(conn, rid)[ids[0]].status == "approved"


def test_validate_param():
    validate_param("Advance Exam - 4")
    for bad in ["a\nb", "a\tb", "a     b", ""]:
        with pytest.raises(ValueError):
            validate_param(bad)


def test_secrets_not_in_db(conn):
    save_secrets({"access_token": "SECRET-TOKEN-123"})
    assert load_secrets()["access_token"] == "SECRET-TOKEN-123"
    assert "SECRET-TOKEN-123" not in "\n".join(conn.iterdump())
    if os.name == "posix":
        assert oct(secrets_path().stat().st_mode)[-3:] == "600"
