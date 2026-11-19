"""Single-owner password: only a salted scrypt hash is stored."""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3

from marksapp import audit
from marksapp.settings import _put, get_setting

_N, _R, _P = 16384, 8, 1
MIN_LENGTH = 8


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), digest)


def password_is_set(conn: sqlite3.Connection) -> bool:
    return bool(get_setting(conn, "password_hash"))


def set_password(conn: sqlite3.Connection, pw: str) -> None:
    if len(pw) < MIN_LENGTH:
        raise ValueError("Password must be at least 8 characters")
    _put(conn, "password_hash", hash_password(pw))
    audit.log(conn, "password_set")


def check_login(conn: sqlite3.Connection, pw: str) -> bool:
    stored = get_setting(conn, "password_hash")
    ok = bool(stored) and verify_password(pw, stored)
    audit.log(conn, "login" if ok else "login_failed")
    return ok
