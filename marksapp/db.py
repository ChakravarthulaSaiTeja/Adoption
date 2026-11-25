"""SQLite storage: one file in the data folder, created on first use."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS students (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL,
  phone TEXT, phone_raw TEXT, stud_id TEXT UNIQUE, name_in_marks TEXT, section TEXT,
  active INTEGER NOT NULL DEFAULT 1, notes TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contact_imports (
  id INTEGER PRIMARY KEY, filename TEXT, file_hash TEXT, imported_at TEXT, row_count INTEGER);
CREATE TABLE IF NOT EXISTS ignored_ids (
  stud_id TEXT PRIMARY KEY, name_in_file TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS layouts (signature TEXT PRIMARY KEY, column_map TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rounds (id INTEGER PRIMARY KEY, label TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exams (
  id INTEGER PRIMARY KEY, round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  test_name TEXT, test_date TEXT, display_name TEXT NOT NULL, exam_type TEXT NOT NULL,
  exam_number INTEGER, sort_order INTEGER NOT NULL,
  max_maths REAL, max_physics REAL, max_chemistry REAL, max_total REAL,
  filename TEXT NOT NULL, file_hash TEXT NOT NULL, via_ocr INTEGER NOT NULL DEFAULT 0,
  imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marks (
  id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  row_no INTEGER NOT NULL, stud_id TEXT NOT NULL, name_in_file TEXT NOT NULL, section TEXT,
  maths TEXT NOT NULL, physics TEXT NOT NULL, chemistry TEXT NOT NULL, total_in_file TEXT NOT NULL,
  total_choice TEXT, edited INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS marks_stud_id ON marks(stud_id);
CREATE TABLE IF NOT EXISTS unreadable_rows (
  id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  row_no INTEGER NOT NULL, raw_text TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, round_id INTEGER NOT NULL REFERENCES rounds(id),
  student_id INTEGER NOT NULL REFERENCES students(id), phone TEXT NOT NULL, body TEXT NOT NULL,
  body_hash TEXT NOT NULL, status TEXT NOT NULL, method TEXT, api_message_id TEXT, error TEXT,
  approved_at TEXT, sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  UNIQUE(round_id, student_id));
CREATE TABLE IF NOT EXISTS sent_log (
  id INTEGER PRIMARY KEY, message_id INTEGER, round_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  phone TEXT NOT NULL, body TEXT NOT NULL, method TEXT, api_message_id TEXT, sent_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
"""


def data_dir() -> Path:
    # Default: the data folder next to the app, whichever folder the app was started from.
    path = Path(os.environ.get("MARKSAPP_DATA_DIR") or APP_DIR / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(path: str | Path | None = None, check_same_thread: bool = True) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else data_dir() / "marks.db"
    conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn
