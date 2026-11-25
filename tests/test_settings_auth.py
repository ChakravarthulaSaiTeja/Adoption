import pytest

from marksapp import audit, auth
from marksapp.settings import get_setting, set_setting


def test_defaults_and_override(conn):
    assert get_setting(conn, "link_kind") == "desktop"
    m = get_setting(conn, "message")
    m["include_name"] = True  # mutating the copy must not leak into defaults
    assert get_setting(conn, "message")["include_name"] is False
    set_setting(conn, "message", m)
    assert get_setting(conn, "message")["include_name"] is True


def test_default_message_format_exact(conn):
    m = get_setting(conn, "message")
    assert m["exam_block"] == ("*{exam} Marks*\n\nMaths - {maths}\nPhysics - {physics}\n"
                               "Chemistry - {chemistry}\n\n*Total Marks - {total}*")
    assert m["separator"] == "\n\n" and m["name_line"] == "*{name}*"


def test_setting_change_audited_without_value(conn):
    set_setting(conn, "link_kind", "web")
    row = audit.recent(conn)[0]
    assert row["action"] == "settings_changed" and "web" not in row["details"]


def test_password(conn):
    assert not auth.password_is_set(conn)
    with pytest.raises(ValueError):
        auth.set_password(conn, "short")
    auth.set_password(conn, "correct horse")
    assert auth.password_is_set(conn)
    assert auth.check_login(conn, "correct horse") and not auth.check_login(conn, "wrong pass")
    stored = conn.execute("select value from settings where key='password_hash'").fetchone()[0]
    assert "correct horse" not in stored and stored.startswith('"scrypt$')
