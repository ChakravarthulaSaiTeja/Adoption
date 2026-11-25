from streamlit.testing.v1 import AppTest

from marksapp.messages import message_settings
from marksapp.outbox import approve
from marksapp.secrets_store import load_secrets
from marksapp.settings import get_setting, set_setting
from tests.helpers import linked_round

TOKEN = "SECRET-TOKEN-ABCD1234"


def _at(module):
    return AppTest.from_string(f'''
import importlib
from marksapp.ui.common import get_conn
importlib.import_module("marksapp.ui.{module}").render(get_conn())
''')


def _all_text(at) -> str:
    parts = []
    for kind in ("markdown", "caption", "info", "success", "warning", "error", "code", "text_input"):
        for el in getattr(at, kind):
            parts.append(str(getattr(el, "value", "")))
    return "\n".join(parts)


def test_token_never_rendered_back(app_env, conn):
    at = _at("settings_page").run(timeout=30)
    at.text_input(key="api_pnid").input("123456789")
    at.text_input(key="api_token").input(TOKEN)
    at.checkbox(key="api_enabled").check()
    at.button(key="api_save").click().run(timeout=30)
    assert not at.exception
    assert load_secrets()["access_token"] == TOKEN and get_setting(conn, "api")["enabled"] is True
    again = _at("settings_page").run(timeout=30)
    text = _all_text(again)
    assert TOKEN not in text and "1234" in text


def test_api_mode_hidden_when_disabled(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    approve(conn, rid, rr.students, message_settings(conn))
    at = _at("send_page").run(timeout=30)
    assert not at.exception
    assert "send_mode" not in [r.key for r in at.radio]


def test_api_mode_shows_template_preview_when_enabled(app_env, conn, tmp_path):
    api = get_setting(conn, "api")
    api.update(enabled=True, templates={"Advance Exam+Mains Exam": "marks_adv_mains"})
    set_setting(conn, "api", api)
    rid, rr = linked_round(conn, tmp_path)
    approve(conn, rid, rr.students, message_settings(conn))
    at = _at("send_page").run(timeout=30)
    at.radio(key="send_mode").set_value("Through WhatsApp API").run(timeout=30)
    assert not at.exception
    assert "marks_adv_mains" in _all_text(at)
