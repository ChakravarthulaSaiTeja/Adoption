from marksapp.secrets_store import load_secrets, save_secrets
from marksapp.sending.method import remove_api_key, sending_method
from marksapp.settings import get_setting, set_setting


def test_phone_without_key(conn):
    assert sending_method(conn) == "phone"


def test_api_with_key(conn):
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    assert sending_method(conn) == "api"


def test_key_without_phone_number_id_is_phone(conn):
    save_secrets({"access_token": "T"})
    assert sending_method(conn) == "phone"


def test_enabled_flag_ignored(conn):
    api = get_setting(conn, "api")
    api["enabled"] = True
    set_setting(conn, "api", api)
    assert sending_method(conn) == "phone"


def test_remove_key(conn):
    save_secrets({"phone_number_id": "1", "access_token": "T"})
    remove_api_key()
    assert sending_method(conn) == "phone" and load_secrets() == {"phone_number_id": "1"}
