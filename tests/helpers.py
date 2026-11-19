"""Shared test helpers that build realistic state through the real code paths."""
from __future__ import annotations

from tests.fixtures import builders


def seed_contacts(conn, tmp_path) -> dict[str, int]:
    from marksapp.contacts import apply_contact_diff, detect_contact_columns, diff_contacts, parse_contacts
    from marksapp.readers.grid import file_hash, load_grid
    path = tmp_path / "contacts.xlsx"
    builders.write_contacts_xlsx(path)
    data = path.read_bytes()
    grid = load_grid(data, path.name)
    header_row, name_col, phone_col, section_col = detect_contact_columns(grid)
    rows = parse_contacts(grid, header_row, name_col, phone_col, section_col)
    apply_contact_diff(conn, diff_contacts(conn, rows), path.name, file_hash(data))
    return {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM students")}
