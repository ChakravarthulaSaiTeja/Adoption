import json

from marksapp import audit
from marksapp.db import data_dir, init_db


def test_tables_created_and_idempotent(conn):
    init_db(conn)
    init_db(conn)
    names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"settings", "students", "contact_imports", "ignored_ids", "layouts", "rounds", "exams",
            "marks", "unreadable_rows", "messages", "audit_log"} <= names


def test_foreign_keys_on(conn):
    assert conn.execute("pragma foreign_keys").fetchone()[0] == 1


def test_data_dir_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKSAPP_DATA_DIR", str(tmp_path / "x"))
    assert data_dir() == tmp_path / "x" and (tmp_path / "x").is_dir()


def test_db_file_lives_in_data_dir(conn, tmp_path):
    assert (tmp_path / "data" / "marks.db").exists()


def test_audit_log(conn):
    audit.log(conn, "first", a=1)
    audit.log(conn, "second", b="x")
    rows = audit.recent(conn)
    assert [r["action"] for r in rows] == ["second", "first"]
    assert json.loads(rows[0]["details"]) == {"b": "x"}


def test_data_dir_default_is_next_to_the_app(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.delenv("MARKSAPP_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # started from some other folder
    assert data_dir() == Path(__file__).resolve().parent.parent / "data"
