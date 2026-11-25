"""WhatsApp API credentials, kept in a private local file — never in the database."""
from __future__ import annotations

import json
import os
from pathlib import Path

from marksapp.db import data_dir


def secrets_path() -> Path:
    return data_dir() / "secrets.json"


def load_secrets() -> dict:
    path = secrets_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_secrets(d: dict) -> None:
    path = secrets_path()
    text = json.dumps(d, indent=2)
    if os.name == "posix":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(path, 0o600)
    else:
        path.write_text(text, encoding="utf-8")
