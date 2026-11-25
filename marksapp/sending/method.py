"""Which way to send: the owner's rule.

If a WhatsApp Business API key is saved (Phone Number ID + access token), the app
sends through the API. If not, it uses the normal method: the owner's own WhatsApp.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

from marksapp.secrets_store import load_secrets, save_secrets


def sending_method(conn: sqlite3.Connection) -> Literal["api", "phone"]:
    s = load_secrets()
    return "api" if s.get("phone_number_id") and s.get("access_token") else "phone"


def remove_api_key() -> None:
    s = load_secrets()
    s.pop("access_token", None)
    save_secrets(s)
