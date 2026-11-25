from streamlit.testing.v1 import AppTest

from marksapp.messages import message_settings
from marksapp.outbox import approve
from marksapp.secrets_store import load_secrets, save_secrets
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


def _approved_round(conn, tmp_path):
    from marksapp.contacts import confirm_shared_number
    rid, rr = linked_round(conn, tmp_path)
    confirm_shared_number(conn, "+919876543205")
    from marksapp.results import build_results
    approve(conn, rid, build_results(conn, rid).students, message_settings(conn))
    return rid


def _set_templates(conn):
    api = get_setting(conn, "api")
    api["templates"] = {"Advance Exam+Mains Exam": "marks_adv_mains"}
    set_setting(conn, "api", api)


def _keys(at):
    return [b.key or "" for b in at.button]


def test_token_never_rendered_back(app_env, conn):
    from marksapp.sending.method import sending_method
    at = _at("settings_page").run(timeout=30)
    at.text_input(key="api_pnid").input("123456789")
    at.text_input(key="api_token").input(TOKEN)
    at.button(key="api_save").click().run(timeout=30)
    assert not at.exception
    assert load_secrets()["access_token"] == TOKEN and sending_method(conn) == "api"
    again = _at("settings_page").run(timeout=30)
    text = _all_text(again)
    assert TOKEN not in text and "1234" in text
    assert "api_enabled" not in [c.key for c in again.checkbox]


def test_send_page_phone_mode_without_key(app_env, conn, tmp_path):
    _approved_round(conn, tmp_path)
    at = _at("send_page").run(timeout=30)
    assert not at.exception
    assert "api_send_all" not in _keys(at) and any(k.startswith("mark_sent_") for k in _keys(at))
    html = _all_text(at)
    assert 'class="wa-btn"' in html and 'target="_self"' in html and "whatsapp://send?phone=91" in html


def test_send_page_api_mode_with_key(app_env, conn, tmp_path):
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    _set_templates(conn)
    _approved_round(conn, tmp_path)
    at = _at("send_page").run(timeout=30)
    assert not at.exception and "api_send_all" in _keys(at)
    assert "marks_adv_mains" in _all_text(at)
    assert not any(k.startswith("mark_sent_") for k in _keys(at))


def test_api_without_template_offers_normal_method(app_env, conn, tmp_path):
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    _approved_round(conn, tmp_path)
    at = _at("send_page").run(timeout=30)
    assert not at.exception
    assert any("template" in i.value for i in at.info)
    assert any(k.startswith("mark_sent_") for k in _keys(at))


def test_use_phone_instead_toggle(app_env, conn, tmp_path):
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    _set_templates(conn)
    _approved_round(conn, tmp_path)
    at = _at("send_page").run(timeout=30)
    at.toggle(key="use_phone_instead").set_value(True).run(timeout=30)
    assert not at.exception and any(k.startswith("mark_sent_") for k in _keys(at))


def test_settings_remove_api_key(app_env, conn):
    from marksapp.sending.method import sending_method
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    at = _at("settings_page").run(timeout=30)
    at.button(key="api_remove").click().run(timeout=30)
    assert not at.exception and sending_method(conn) == "phone"


def _make_unknown(conn, rid):
    from marksapp.outbox import get_outbox, mark_sending, mark_unknown
    rec = sorted(get_outbox(conn, rid).values(), key=lambda r: r.id)[0]
    mark_sending(conn, rec.id)
    mark_unknown(conn, rec.id, "No clear answer")
    return rec


def test_unknown_messages_visible_without_api_key(app_env, conn, tmp_path):
    rid = _approved_round(conn, tmp_path)
    rec = _make_unknown(conn, rid)
    at = _at("send_page").run(timeout=30)
    assert not at.exception and f"arr_{rec.id}" in _keys(at) and f"res_{rec.id}" in _keys(at)
    from marksapp.outbox import get_outbox
    from marksapp.ui.send_page import send_totals
    assert send_totals(get_outbox(conn, rid)) == (0, 5)  # 5 approved; the unknown one counts as not sent


def test_unknown_messages_visible_with_phone_toggle(app_env, conn, tmp_path):
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    _set_templates(conn)
    rid = _approved_round(conn, tmp_path)
    rec = _make_unknown(conn, rid)
    at = _at("send_page").run(timeout=30)
    at.toggle(key="use_phone_instead").set_value(True).run(timeout=30)
    assert not at.exception and f"arr_{rec.id}" in _keys(at)
