# Student Marks to Parents on WhatsApp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Streamlit app that reads a contact list and biweekly marks files, links every marks row to the right student, builds one WhatsApp message per student, and sends only owner-approved messages. Sending is from the owner's phone first, and through the WhatsApp Cloud API later.

**Architecture:**
- **Domain package `marksapp/`:** one module per concern (marks values, phones, names, readers, matching, rounds, results, messages, outbox, reports). Each is tested on its own. Most logic is pure functions over dataclasses.
- **Storage:** SQLite stores everything. The round's links, totals and statuses are recomputed from the database on every page view, so Streamlit reruns never hold hidden state.
- **UI:** the Streamlit pages are thin: they call domain functions and render results.

**Tech Stack:**
- Python ≥ 3.10, Streamlit ≥ 1.40, pandas ≥ 2.1, openpyxl ≥ 3.1, xlrd ≥ 2.0.1, pdfplumber ≥ 0.11, RapidFuzz ≥ 3.6, requests ≥ 2.31
- Stage 2: PyMuPDF ≥ 1.24, pytesseract ≥ 0.3.10
- Dev: pytest ≥ 8, reportlab ≥ 4.0

**Spec:** `docs/superpowers/specs/2026-11-19-student-marks-whatsapp-design.md`

**Deviations from spec, decided while planning:**
- **No "Opened" status.** Streamlit cannot observe a click on a link, so phone mode goes Approved → Sent or Failed, recorded when the owner confirms.
- **`students.name_in_marks`.** When a link is confirmed, the student's name *as written in the marks file* is saved too. The later cross-check compares against both names. Without it, a contact saved as "Meghana Sri" would raise a "name differs" flag against "PALLAPU MEGHANA SRI" every round.
- **API templates use fixed exam words.** Exam names are fixed text in the API template ("*Advance Exam - {{1}} Marks*"), with only the exam number as a variable. Meta rejects templates that start with a variable.

## Global Constraints

**Platform and data**
- Python ≥ 3.10. Must run on Windows and macOS: use `pathlib` everywhere, and guard `chmod` with `os.name == "posix"`.
- `.streamlit/config.toml` sets `server.address = "127.0.0.1"` and `browser.gatherUsageStats = false`.
- Data lives in `data/` (overridable with the environment variable `MARKSAPP_DATA_DIR`). `data/` is git-ignored, and tests always use a temporary directory.
- **No real student data anywhere in the repo.** Fixtures use the made-up names in Task 6.

**Marks and numbers**
- Missing marks are never 0: they are `Mark("NA")`. Absent is `Mark("AB")`. Negative marks are valid.
- Phone numbers are stored as `+91XXXXXXXXXX` (10 digits starting 6–9), or `NULL` with the raw text kept.
- **Every function that writes commits its own work** (`with conn:`), because the UI and the tests use separate connections to the same file.

**Matching**
- Thresholds: `CANDIDATE_FLOOR = 70.0`, `CROSSCHECK_MIN = 85.0`, `MAX_CANDIDATES = 3`.
- **A fuzzy score never links a student.** Only an exact name-key match can be *proposed*, and every link is saved only by `confirm_links` after the owner confirms.

**Sending**
- A message can be sent only from a `messages` row whose `body_hash` equals `content_hash(phone, freshly rendered body)` at send time.
- Default message format, exactly:
  `exam_block = "*{exam} Marks*\n\nMaths - {maths}\nPhysics - {physics}\nChemistry - {chemistry}\n\n*Total Marks - {total}*"`
  `separator = "\n\n"`, `include_name = False`, `name_line = "*{name}*"`
- No unofficial WhatsApp automation dependencies (pywhatkit, selenium, playwright in app code, etc.).

## Review Focus

1. **Real Excel files with merged header cells** ("Mat_Q's" spanning 4 columns, "TOT" above "180") should still map columns correctly → Task 7 `test_merged_header_cells_xlsx`.
2. **STUD_IDs stored as Excel floats or with leading zeros** (`268435197.0`, `"0012345"`) should produce the same ID string from Excel and PDF → Task 6 `test_ids_normalised_across_formats`.
3. **Two numbers in one contact cell** (`"9876543210 / 9123456789"`) should be flagged, never guessed → Task 2 `test_two_numbers_in_one_cell_is_flagged`.
4. **One round mixing exam numbers** (Advance 5 with Mains 4) should show a visible warning → Task 11 `test_round_warns_when_exam_numbers_differ`.
5. **A contact saved under a shorter name** than the marks file uses should be linked once in round one and give clean ID matches afterwards → Task 12 `test_round_two_clean_after_short_contact_name`.

---

## File Structure

```
pyproject.toml, requirements.txt, requirements-dev.txt, .gitignore, README.md
.streamlit/config.toml
app.py                         Streamlit entry: login gate + navigation
marksapp/
  __init__.py
  values.py                    Mark (num/AB/NA), parse/encode/decode
  phones.py                    normalise_phone, pretty_phone
  names.py                     clean_name, name_key, similarity, title_name
  db.py                        data_dir, connect, init_db (schema)
  audit.py                     log, recent
  settings.py                  DEFAULTS, get_setting, set_setting
  auth.py                      password hashing + login helpers
  examnames.py                 suggest_exam_name
  contacts.py                  contact import/diff/apply, student edits
  matching.py                  pure matching engine
  rounds.py                    rounds/exams/marks storage, links, layouts, warnings
  results.py                   per-student results + issues, total choice, mark edits
  messages.py                  MessageSettings, render_message, content_hash
  outbox.py                    approvals, status transitions, phone links
  reports.py                   round report, history, Excel export
  secrets_store.py             (stage 3) local secrets file
  readers/__init__.py
  readers/grid.py              load_grid, grid_lines, file_hash, clean_id
  readers/marks_layout.py      header detection + row parsing
  readers/ocr.py               (stage 2) OCR to grid
  sending/__init__.py
  sending/api.py               (stage 3) Cloud API client + batch send
  ui/__init__.py
  ui/common.py                 get_conn, login_gate, round picker
  ui/contacts_page.py, ui/round_page.py, ui/attention_page.py,
  ui/preview_page.py, ui/send_page.py, ui/reports_page.py, ui/settings_page.py
docs/whatsapp-api-setup.md     (stage 3) owner's Meta setup guide
tests/
  conftest.py                  tmp data dir, conn fixture, fixture files
  fixtures/builders.py         made-up sample data + xlsx/csv/pdf writers
  helpers.py                   seed_contacts, seed_round
  test_*.py                    one per module
```

---

## Stage 1 — Core (usable for real rounds)

### Task 1: Project scaffold and `Mark` values

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `marksapp/__init__.py`, `marksapp/values.py`, `tests/conftest.py` (empty for now)
- Test: `tests/test_values.py`

**Interfaces:**
- Produces:
  - `Mark(kind: Literal["num","AB","NA"], value: float | None = None)`: a frozen dataclass.
  - `Mark.display() -> str`
  - `Mark.encode() -> str`
  - `decode_mark(s: str) -> Mark`
  - `parse_mark(raw: object) -> Mark`
  - Constants `NA = Mark("NA")` and `AB = Mark("AB")`.

- [ ] **Step 1: Scaffold**

`.gitignore`: `data/`, `__pycache__/`, `.venv/`, `*.db`, `.pytest_cache/`.

`pyproject.toml`: package `marksapp`, `requires-python = ">=3.10"`, and `[tool.pytest.ini_options] testpaths = ["tests"]`.

`requirements.txt`: `streamlit>=1.40`, `pandas>=2.1`, `openpyxl>=3.1`, `xlrd>=2.0.1`, `pdfplumber>=0.11`, `rapidfuzz>=3.6`, `requests>=2.31`.

`requirements-dev.txt`: `-r requirements.txt`, `pytest>=8`, `reportlab>=4.0`.

Create `.venv` and install `requirements-dev.txt`.

- [ ] **Step 2: Write the failing tests**

```python
from marksapp.values import Mark, parse_mark, decode_mark, NA, AB

def test_integers_and_negatives():
    assert parse_mark(41) == Mark("num", 41.0)
    assert parse_mark("-7") == Mark("num", -7.0)
    assert parse_mark("−7") == Mark("num", -7.0)      # unicode minus
    assert parse_mark(" 60 ") == Mark("num", 60.0)
    assert parse_mark(0) == Mark("num", 0.0)

def test_display():
    assert parse_mark(41).display() == "41"
    assert parse_mark(-7.0).display() == "-7"
    assert parse_mark("41.5").display() == "41.5"
    assert AB.display() == "AB" and NA.display() == "NA"

def test_absent_words():
    for raw in ["AB", "ab ", "Absent", "A"]:
        assert parse_mark(raw) == AB

def test_missing_is_never_zero():
    for raw in [None, "", "  ", float("nan"), "--", "x12"]:
        assert parse_mark(raw) == NA

def test_encode_roundtrip():
    for m in [Mark("num", 41.0), Mark("num", -7.0), Mark("num", 41.5), AB, NA]:
        assert decode_mark(m.encode()) == m
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/test_values.py -v`
Expected: FAIL (`ModuleNotFoundError: marksapp.values`).

- [ ] **Step 4: Implement `marksapp/values.py`**

- `encode()` gives `"num:<repr>"`, `"AB"` or `"NA"`.
- `display()` drops a trailing `.0`.
- `parse_mark`:
  - booleans → NA
  - int/float (NaN → NA) → num
  - strings: strip, replace `−` with `-`, then upper-case
    - in `{"AB","ABSENT","A"}` → AB
    - `float()` succeeds → num
    - otherwise → NA

- [ ] **Step 5: Run tests — expect PASS.**

Run: `pytest tests/test_values.py -v`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements*.txt .gitignore marksapp tests
git commit -m "feat: project scaffold and Mark value parsing"
```

---

### Task 2: Phone normalisation

**Files:**
- Create: `marksapp/phones.py`
- Test: `tests/test_phones.py`

**Interfaces:**
- Produces:
  - `PhoneResult(ok: bool, e164: str | None, raw: str, problem: str | None)`: a frozen dataclass.
  - `normalise_phone(raw: object) -> PhoneResult`
  - `pretty_phone(e164: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
from marksapp.phones import normalise_phone, pretty_phone

def test_accepted_forms():
    for raw in ["9876543210", "+91 98765-43210", "(+91) 98765 43210",
                "919876543210", "09876543210", 9876543210, 9876543210.0, "9.87654321E9"]:
        r = normalise_phone(raw)
        assert r.ok and r.e164 == "+919876543210", raw

def test_rejected_forms():
    assert normalise_phone("5876543210").problem == "Must start with 6, 7, 8 or 9"
    assert normalise_phone("98765").problem == "Must be 10 digits"
    assert normalise_phone(None).problem == "Missing"
    assert normalise_phone("").problem == "Missing"
    assert normalise_phone("+1 415 555 0100").problem == "Not an Indian mobile number"

def test_two_numbers_in_one_cell_is_flagged():
    r = normalise_phone("9876543210 / 9123456789")
    assert not r.ok and r.problem == "More than one number"

def test_raw_kept_and_pretty():
    assert normalise_phone(" 98765 43210 ").raw == "98765 43210"
    assert pretty_phone("+919876543210") == "+91 98765 43210"
```

- [ ] **Step 2: Run to verify it fails.**

Run: `pytest tests/test_phones.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `marksapp/phones.py`**

Rules are checked in this order:
1. Numbers (int/float/scientific-notation strings) → integer string.
2. Two or more groups of 10+ digits, separated by `/`, `,`, `;`, ` or ` or `&` → "More than one number".
3. Strip everything except digits and a leading `+`.
4. `+` followed by a country code other than 91 → "Not an Indian mobile number".
5. Drop the `+91` / `91` prefix (12 digits) or `0` (11 digits).
6. Length ≠ 10 → "Must be 10 digits".
7. First digit not 6–9 → "Must start with 6, 7, 8 or 9".

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/phones.py tests/test_phones.py
git commit -m "feat: Indian mobile number normalisation"
```

---

### Task 3: Name cleaning and similarity

**Files:**
- Create: `marksapp/names.py`
- Test: `tests/test_names.py`

**Interfaces:**
- Produces:
  - `clean_name(raw: object) -> str`
  - `name_key(raw: object) -> str`
  - `similarity(a: str, b: str) -> float` (0–100)
  - `title_name(raw: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
from marksapp.names import clean_name, name_key, similarity, title_name

def test_clean():
    assert clean_name("  Pallapu.  Meghana-Sri ") == "PALLAPU MEGHANA SRI"
    assert clean_name("GORANTLA SAI\nKARTHIK") == "GORANTLA SAI KARTHIK"
    assert clean_name("K.Ravi") == "K RAVI"
    assert clean_name(None) == ""

def test_key_ignores_order_and_dots():
    assert name_key("PALLAPU MEGHANA SRI") == name_key("Meghana Sri Pallapu")
    assert name_key("K. Ravi Teja") == name_key("RAVI TEJA K")

def test_spelling_variant_scores_high():
    assert similarity("GORANTLA SAI KARTHIK", "Gorantla Sai Kartik") >= 85

def test_initial_vs_full_word_is_candidate_but_capped():
    s = similarity("V NIHARIKA DEVI", "Niharika Devi Vanga")
    assert 85 <= s <= 90

def test_siblings_are_not_candidates():
    assert similarity("NAKKA RAVI TEJA", "Nakka Ravi Kiran") < 70

def test_missing_surname_is_candidate_not_exact():
    assert 70 <= similarity("PALLAPU MEGHANA SRI", "Pallapu Meghana") < 100

def test_identical_after_cleaning_is_100():
    assert similarity("PALLAPU MEGHANA SRI", "Meghana Sri Pallapu") == 100

def test_title_name():
    assert title_name("PALLAPU MEGHANA SRI") == "Pallapu Meghana Sri"
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `marksapp/names.py`**

- `clean_name`: replace `. , - _ ' \n \t` with spaces, upper-case, collapse whitespace.
- `name_key`: the cleaned words, sorted and joined with a space.
- `similarity`:
  - `base = rapidfuzz.fuzz.token_sort_ratio(clean a, clean b)`.
  - Initials pass: if one side has single-letter words and each can be paired with a *distinct* unused word on the other side starting with that letter, expand them and take `min(90, token_sort_ratio(expanded, other))`.
  - Return `max(base, initials_score)`.
  - Return 0 if either side is empty.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/names.py tests/test_names.py
git commit -m "feat: name cleaning, keys and similarity"
```

---

### Task 4: Database schema and audit log

**Files:**
- Create: `marksapp/db.py`, `marksapp/audit.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `data_dir() -> Path`: `$MARKSAPP_DATA_DIR` or `./data`, created if missing.
  - `connect(path: str | Path | None = None, check_same_thread: bool = True) -> sqlite3.Connection`
    - default path: `data_dir()/marks.db`
    - `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`
    - calls `init_db`
  - `init_db(conn) -> None`
  - `now_iso() -> str`: local time, seconds precision.
  - `audit.log(conn, action: str, **details) -> None`
  - `audit.recent(conn, limit: int = 200) -> list[sqlite3.Row]`: newest first.
  - conftest fixture `conn`: sets `MARKSAPP_DATA_DIR` to `tmp_path` and yields `connect()`.

**Schema** (exact column names; later tasks depend on them):

```sql
settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)                       -- JSON values
students(id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL,
  phone TEXT, phone_raw TEXT, stud_id TEXT UNIQUE, name_in_marks TEXT, section TEXT,
  active INTEGER NOT NULL DEFAULT 1, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
contact_imports(id INTEGER PRIMARY KEY, filename TEXT, file_hash TEXT, imported_at TEXT, row_count INTEGER)
ignored_ids(stud_id TEXT PRIMARY KEY, name_in_file TEXT, created_at TEXT NOT NULL)
layouts(signature TEXT PRIMARY KEY, column_map TEXT NOT NULL)            -- JSON {field: col}
rounds(id INTEGER PRIMARY KEY, label TEXT NOT NULL, created_at TEXT NOT NULL)
exams(id INTEGER PRIMARY KEY, round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  test_name TEXT, test_date TEXT, display_name TEXT NOT NULL, exam_type TEXT NOT NULL,
  exam_number INTEGER, sort_order INTEGER NOT NULL,
  max_maths REAL, max_physics REAL, max_chemistry REAL, max_total REAL,
  filename TEXT NOT NULL, file_hash TEXT NOT NULL, via_ocr INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL)
marks(id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  row_no INTEGER NOT NULL, stud_id TEXT NOT NULL, name_in_file TEXT NOT NULL, section TEXT,
  maths TEXT NOT NULL, physics TEXT NOT NULL, chemistry TEXT NOT NULL, total_in_file TEXT NOT NULL,  -- Mark.encode()
  total_choice TEXT, edited INTEGER NOT NULL DEFAULT 0)
unreadable_rows(id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  row_no INTEGER NOT NULL, raw_text TEXT NOT NULL, reason TEXT NOT NULL)
messages(id INTEGER PRIMARY KEY, round_id INTEGER NOT NULL REFERENCES rounds(id),
  student_id INTEGER NOT NULL REFERENCES students(id), phone TEXT NOT NULL, body TEXT NOT NULL,
  body_hash TEXT NOT NULL, status TEXT NOT NULL, method TEXT, api_message_id TEXT, error TEXT,
  approved_at TEXT, sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0, UNIQUE(round_id, student_id))
audit_log(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL)  -- JSON
```

- [ ] **Step 1: Write the failing tests**

```python
def test_tables_created_and_idempotent(conn):
    from marksapp.db import init_db
    init_db(conn); init_db(conn)
    names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"settings","students","contact_imports","ignored_ids","layouts","rounds","exams",
            "marks","unreadable_rows","messages","audit_log"} <= names

def test_foreign_keys_on(conn):
    assert conn.execute("pragma foreign_keys").fetchone()[0] == 1

def test_data_dir_env(tmp_path, monkeypatch):
    from marksapp.db import data_dir
    monkeypatch.setenv("MARKSAPP_DATA_DIR", str(tmp_path / "x"))
    assert data_dir() == tmp_path / "x" and (tmp_path / "x").is_dir()

def test_audit_log(conn):
    from marksapp import audit
    audit.log(conn, "first", a=1); audit.log(conn, "second", b="x")
    rows = audit.recent(conn)
    assert [r["action"] for r in rows] == ["second", "first"]
    assert json.loads(rows[0]["details"]) == {"b": "x"}
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `db.py` and `audit.py`, and the `conn` fixture in `conftest.py`.**

`audit.log` commits.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/db.py marksapp/audit.py tests/conftest.py tests/test_db.py
git commit -m "feat: SQLite schema and audit log"
```

---

### Task 5: Settings and password

**Files:**
- Create: `marksapp/settings.py`, `marksapp/auth.py`
- Test: `tests/test_settings_auth.py`

**Interfaces:**
- Produces:
  - `settings.DEFAULTS: dict`
  - `get_setting(conn, key: str) -> Any`: stored JSON value or a deep copy of `DEFAULTS[key]`.
  - `set_setting(conn, key: str, value: Any) -> None`: audits `"settings_changed"` with the key only, never the value.
  - `auth.hash_password(pw: str) -> str`
  - `auth.verify_password(pw: str, stored: str) -> bool`
  - `auth.password_is_set(conn) -> bool`
  - `auth.set_password(conn, pw: str) -> None`: `ValueError("Password must be at least 8 characters")` if `len < 8`.
  - `auth.check_login(conn, pw: str) -> bool`

`DEFAULTS`:

```python
{
  "exam_rules": [["ADV", "Advance Exam"], ["MAIN", "Mains Exam"]],
  "message": {"exam_block": "*{exam} Marks*\n\nMaths - {maths}\nPhysics - {physics}\nChemistry - {chemistry}\n\n*Total Marks - {total}*",
              "separator": "\n\n", "include_name": False, "name_line": "*{name}*"},
  "link_kind": "wa.me",
  "api": {"enabled": False, "api_version": "v24.0", "language": "en", "templates": {}, "pause_seconds": 2.0},
}
```

- [ ] **Step 1: Write the failing tests**

```python
def test_defaults_and_override(conn):
    from marksapp.settings import get_setting, set_setting
    assert get_setting(conn, "link_kind") == "wa.me"
    m = get_setting(conn, "message"); m["include_name"] = True       # mutating copy must not leak
    assert get_setting(conn, "message")["include_name"] is False
    set_setting(conn, "message", m)
    assert get_setting(conn, "message")["include_name"] is True

def test_password(conn):
    from marksapp import auth
    assert not auth.password_is_set(conn)
    with pytest.raises(ValueError): auth.set_password(conn, "short")
    auth.set_password(conn, "correct horse")
    assert auth.check_login(conn, "correct horse") and not auth.check_login(conn, "wrong pass")
    stored = conn.execute("select value from settings where key='password_hash'").fetchone()[0]
    assert "correct horse" not in stored and stored.startswith('"scrypt$')
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement.**

- Use `hashlib.scrypt(n=16384, r=8, p=1)` with a 16-byte random salt.
- Format: `scrypt$16384$8$1$<salt hex>$<hash hex>`, stored under the settings key `password_hash`.
- Compare with `hmac.compare_digest`.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/settings.py marksapp/auth.py tests/test_settings_auth.py
git commit -m "feat: settings store and password login"
```

---

### Task 6: File grids and sample fixtures

**Files:**
- Create: `marksapp/readers/__init__.py`, `marksapp/readers/grid.py`, `tests/fixtures/__init__.py`, `tests/fixtures/builders.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_grid.py`

**Interfaces:**
- Produces:
  - `Grid = list[list[str]]`
  - `load_grid(data: bytes, filename: str) -> Grid`
  - `grid_lines(grid: Grid) -> list[str]`
  - `file_hash(data: bytes) -> str` (sha256 hex)
  - `clean_id(raw: object) -> str`
  - `class UnsupportedFile(Exception)`
  - `class NoTextInPdf(Exception)`
- Produces (tests):
  - `builders.SAMPLE_ROWS`
  - `builders.MAINS_ROWS`: the same students, with each mark shifted by `(+20, +10, +5)` and the total by `+35`.
  - `builders.marks_grid(test_name="JEE(Adv)/WTA-4", test_date="17-August-2026", maxes=(60, 60, 60, 180), rows=SAMPLE_ROWS, footer=None, repeat_header_after=None) -> list[list]`
  - `builders.write_xlsx(grid, path, merge_headers=False)`
  - `builders.write_csv(grid, path)`
  - `builders.write_pdf(grid, path)`
  - `builders.write_blank_pdf(path)`
  - `builders.CONTACTS`
  - `builders.write_contacts_xlsx(path, rows=CONTACTS)`
  - conftest fixture `marks_files(tmp_path) -> dict[str, Path]` with keys `"xlsx"`, `"csv"`, `"pdf"`, `"mains_xlsx"`, `"mains_pdf"`. Mains files use `test_name="JEE(Main)/WTM-4"`, `maxes=(100, 100, 100, 300)` and `MAINS_ROWS`.

**Made-up sample data** (the only student data allowed in the repo):

```python
SAMPLE_ROWS = [  # stud_id, name, sec, mat, phy, che, tot
  ("100000001", "PALLAPU MEGHANA SRI", "PR4", 41, 32, 17, 90),
  ("100000002", "GORANTLA SAI KARTHIK", "PR4", 50, 25, 12, 87),
  ("100000003", "MUDDANA VENKATA SAI SRINIVAS RAO", "PR3", 23, 16, -7, 32),
  ("100000004", "V NIHARIKA DEVI", "PR3", 20, 14, -6, 28),
  ("100000005", "NAKKA RAVI TEJA", "PR4", 30, 28, 12, 70),
  ("100000006", "NAKKA RAVI KIRAN", "PR4", 22, 25, 10, 57),
  ("100000007", "KOLLURI ANJALI", "PR3", 0, 0, 0, 0),
  ("100000008", "SYED AFREEN", "PR4", 12, 8, 5, 25),
]
CONTACTS = [  # name, number as typed
  ("Meghana Sri Pallapu", "98765 43201"), ("Gorantla Sai Kartik", "+91 98765-43202"),
  ("Muddana Venkata Sai Srinivas Rao", "9876543203"), ("Niharika Devi Vanga", "09876543204"),
  ("Nakka Ravi Teja", "9876543205"), ("Nakka Ravi Kiran", "9876543205"),   # siblings share
  ("Kolluri Anjali", "98765432"), ("Syed Afreen", 9876543208.0),          # bad number; float
]
```

**`marks_grid` layout** (copies the screenshot):
- Title row `ALL INDIA MARKS ANALYSIS`.
- Rows `["Prog Name:", "Sample Programme"]`, `["Test Date:", test_date]`, `["Test Name:", test_name]`.
- A two-row header:
  - Row 1: `STUD_ID, NAME OF THE STUDENT, SEC, TOT, %, AIR RANK, State Rank, Camp Rank, MAT, MAT RANK, %, Mat_Q's,"","","", PHY, PHY RANK, %, Phy_Q's,"","","", CHE, CHE RANK, %, Che_Q's,"","",""`
  - Row 2: maxes under TOT/MAT/PHY/CHE, and `W, W_Q's, U, U_Q's` under each `_Q's`.
- Data rows fill every column, with made-up ranks, percentages and question lists.

`write_pdf`:
- A landscape reportlab `Table` with a `GRID` style.
- Name cells are `Paragraph`s in a narrow column, so long names wrap onto two lines.
- The title and header block are paragraphs above the table.
- If `repeat_header_after` is set, the header rows repeat on page 2.

`write_xlsx(merge_headers=True)` merges the `_Q's` cells across their 4 columns.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("fmt", ["xlsx", "csv", "pdf"])
def test_sample_loads(marks_files, fmt):
    p = marks_files[fmt]; grid = load_grid(p.read_bytes(), p.name)
    lines = grid_lines(grid)
    assert any("Test Name: JEE(Adv)/WTA-4" in l for l in lines)
    flat = [c for row in grid for c in row]
    assert "100000003" in flat
    assert "MUDDANA VENKATA SAI SRINIVAS RAO" in flat      # wrapped PDF cell joined with a space
    assert "-7" in flat

def test_ids_normalised_across_formats():
    assert clean_id(268435197.0) == "268435197"
    assert clean_id("268435197.0") == "268435197"
    assert clean_id(" 0012345 ") == "12345"
    assert clean_id("PR-0042") == "PR-0042"                # non-numeric kept as is

def test_unsupported(tmp_path):
    with pytest.raises(UnsupportedFile): load_grid(b"x", "marks.docx")

def test_pdf_without_text(tmp_path):
    p = tmp_path / "scan.pdf"; builders.write_blank_pdf(p)
    with pytest.raises(NoTextInPdf): load_grid(p.read_bytes(), p.name)

def test_file_hash_stable():
    assert file_hash(b"abc") == file_hash(b"abc") != file_hash(b"abd")
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `grid.py` and the builders**

`load_grid` dispatches on the file extension:
- `.xlsx`: `pandas.read_excel(header=None, dtype=object, engine="openpyxl")`
- `.xls`: the same with `engine="xlrd"`
- `.csv`: `read_csv(header=None, dtype=str, keep_default_na=False)`
- `.pdf`: pdfplumber.
  - Page 1's text above the first table's bbox becomes one-cell rows.
  - Then `extract_tables()` rows from every page, in order.
  - No chars on any page → `NoTextInPdf`.

Cells:
- `None`/NaN → `""`.
- Integral floats → int string.
- Strings: `\n` → space, then strip.

`clean_id`:
- integral float or numeric string → `str(int(...))`, which strips leading zeros and `.0`
- otherwise → the stripped string

`grid_lines` joins each row's non-empty cells with a space.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/readers tests/fixtures tests/conftest.py tests/test_grid.py
git commit -m "feat: load Excel/CSV/PDF into grids; made-up sample fixtures"
```

---

### Task 7: Marks file layout parser

**Files:**
- Create: `marksapp/readers/marks_layout.py`
- Test: `tests/test_marks_layout.py`

**Interfaces:**
- Consumes: `Grid`, `grid_lines`, `clean_id` (Task 6); `parse_mark`, `Mark` (Task 1).
- Produces:
  - `REQUIRED = ("stud_id", "name", "maths", "physics", "chemistry")`
  - `OPTIONAL = ("section", "total")`
  - `MarksRow(row_no: int, stud_id: str, name: str, section: str, maths: Mark, physics: Mark, chemistry: Mark, total_in_file: Mark)`
  - `UnreadableRow(row_no: int, raw_text: str, reason: str)`
  - `ParsedMarksFile`:
    - `test_name: str | None`, `test_date: str | None`
    - `header_row: int`, `column_map: dict[str, int]`
    - `maxes: dict[str, float | None]`, keys `maths`/`physics`/`chemistry`/`total`
    - `rows: list[MarksRow]`, `unreadable: list[UnreadableRow]`
    - `header_signature: str`, `missing_fields: list[str]`
  - `class LayoutNotFound(Exception)`
  - `parse_marks_grid(grid: Grid, column_map: dict[str, int] | None = None, header_row: int | None = None) -> ParsedMarksFile`

**Column detection** (on header-row cells):
- Normalise each cell: `re.sub(r"[^A-Z0-9]", "", cell.upper())`.
- `label` = that text without trailing digits. The digits, if any, are the max mark.
- Match labels against:
  - `stud_id`: `STUDID STUDENTID ROLLNO ROLLNUMBER ADMNO ADMISSIONNO HTNO`
  - `name`: label contains `NAME`
  - `section`: `SEC SECTION`
  - `total`: `TOT TOTAL TOTALMARKS`
  - `maths`: `MAT MATH MATHS MATHEMATICS`
  - `physics`: `PHY PHYSICS`
  - `chemistry`: `CHE CHEM CHEMISTRY`
- Leftmost match wins, so `MAT RANK` (label `MATRANK`) never matches.
- The header row is the first row with both a `stud_id` cell and a `name` cell. If there is none and no `column_map` was given → `LayoutNotFound`.
- If a label cell has no digits, its max is the numeric cell directly below it.

**Header block:**
- Find the cell matching `(?i)^test\s*name\s*[:\-]?` (likewise `test\s*date`).
- The value is the text after the colon in the same cell, or else the next non-empty cell in that row.

**Rows** (everything after the header row):
- Rows before the first data row are skipped. A data row has a `stud_id` cell matching `^[A-Za-z0-9/\-]{3,}$` that contains a digit, and a non-empty name.
- After the first data row:
  - empty row → skip
  - row containing a `stud_id` header label again → skip (repeated header)
  - data row → `MarksRow` (`row_no` = grid index + 1)
  - otherwise → `UnreadableRow` with reason `"No student ID"` or `"No name"`
- Signature: `sha1("|".join(normalised header cells))`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("fmt", ["xlsx", "csv", "pdf"])
def test_sample_parses(marks_files, fmt):
    p = marks_files[fmt]; f = parse_marks_grid(load_grid(p.read_bytes(), p.name))
    assert f.test_name == "JEE(Adv)/WTA-4" and f.test_date == "17-August-2026"
    assert f.maxes == {"maths": 60, "physics": 60, "chemistry": 60, "total": 180}
    assert len(f.rows) == 8 and f.unreadable == [] and f.missing_fields == []
    r = f.rows[2]
    assert (r.stud_id, r.name, r.section) == ("100000003", "MUDDANA VENKATA SAI SRINIVAS RAO", "PR3")
    assert r.chemistry == Mark("num", -7.0) and r.total_in_file == Mark("num", 32.0)

def test_mains_maxes(marks_files):
    p = marks_files["mains_xlsx"]; f = parse_marks_grid(load_grid(p.read_bytes(), p.name))
    assert f.maxes["total"] == 300 and f.maxes["maths"] == 100

def test_merged_header_cells_xlsx(tmp_path):
    p = tmp_path / "m.xlsx"; builders.write_xlsx(builders.marks_grid(), p, merge_headers=True)
    f = parse_marks_grid(load_grid(p.read_bytes(), p.name))
    assert len(f.rows) == 8 and f.maxes["chemistry"] == 60

def test_footer_is_unreadable_and_repeated_header_skipped():
    g = builders.marks_grid(footer="Generated by analysis system", repeat_header_after=4)
    f = parse_marks_grid(g)
    assert len(f.rows) == 8
    assert [u.reason for u in f.unreadable] == ["No student ID"]

def test_row_without_name_is_unreadable():
    g = builders.marks_grid(); g[-1][1] = ""
    f = parse_marks_grid(g)
    assert len(f.rows) == 7 and f.unreadable[0].reason == "No name"

def test_missing_column_reported():
    g = [[c for i, c in enumerate(row) if i < 22] for row in builders.marks_grid()]  # drop CHE block
    assert parse_marks_grid(g).missing_fields == ["chemistry"]

def test_manual_column_map():
    g = [["Roll", "Student", "M", "P", "C", "Grand"], ["A123", "SYED AFREEN", "12", "8", "5", "25"]]
    f = parse_marks_grid(g, column_map={"stud_id": 0, "name": 1, "maths": 2, "physics": 3,
                                        "chemistry": 4, "total": 5}, header_row=0)
    assert f.rows[0].total_in_file == Mark("num", 25.0)

def test_absent_cell():
    g = builders.marks_grid(); g[-1][8] = "AB"                 # MAT column of last row
    assert parse_marks_grid(g).rows[-1].maths == Mark("AB")

def test_signature_stable():
    a = parse_marks_grid(builders.marks_grid()).header_signature
    b = parse_marks_grid(builders.marks_grid(test_name="JEE(Main)/WTM-4")).header_signature
    assert a == b
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `marksapp/readers/marks_layout.py` to the rules above.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/readers/marks_layout.py tests/test_marks_layout.py
git commit -m "feat: marks file layout detection and row parsing"
```

---

### Task 8: Exam names

**Files:**
- Create: `marksapp/examnames.py`
- Test: `tests/test_examnames.py`

**Interfaces:**
- Produces:
  - `ExamName(exam_type: str, number: int | None, display: str, sort_order: int)`: a frozen dataclass.
  - `suggest_exam_name(test_name: str | None, rules: list[list[str]]) -> ExamName`

- [ ] **Step 1: Write the failing tests**

```python
RULES = [["ADV", "Advance Exam"], ["MAIN", "Mains Exam"]]
def test_examples():
    assert suggest_exam_name("JEE(Adv)/WTA-4", RULES) == ExamName("Advance Exam", 4, "Advance Exam - 4", 0)
    assert suggest_exam_name("JEE(Main)/WTM-4", RULES) == ExamName("Mains Exam", 4, "Mains Exam - 4", 1)
    assert suggest_exam_name("JEE MAINS GT-12", RULES).number == 12
    assert suggest_exam_name("Weekly Test", RULES) == ExamName("Weekly Test", None, "Weekly Test", 2)
    assert suggest_exam_name(None, RULES) == ExamName("Exam", None, "Exam", 2)
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement.**

- The first rule whose keyword is a substring of the upper-cased test name wins, and `sort_order` is that rule's index.
- The number is the last integer in the test name.
- `display = f"{type} - {number}"`, or `type` alone when there is no number.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/examnames.py tests/test_examnames.py
git commit -m "feat: exam display names from test names"
```

---

### Task 9: Contacts import, diff and edits

**Files:**
- Create: `marksapp/contacts.py`, `tests/helpers.py`
- Test: `tests/test_contacts.py`

**Interfaces:**
- Consumes: `normalise_phone`, `PhoneResult` (Task 2); `name_key`, `clean_name` (Task 3); `Grid` (Task 6); `audit.log`, `now_iso` (Task 4).
- Produces:
  - `ContactRow(line_no: int, name: str, phone: PhoneResult, section: str)`
  - `ContactDiff`:
    - `new: list[ContactRow]`
    - `phone_changed: list[tuple[int, ContactRow, str | None]]` (student id, row, old phone)
    - `reactivated: list[int]`, `unchanged: list[int]`, `missing: list[int]`
    - `duplicate_names: list[list[ContactRow]]`
    - `invalid: list[ContactRow]`, `bad_numbers: list[ContactRow]`
    - `shared_numbers: list[list[str]]`
  - `detect_contact_columns(grid: Grid) -> tuple[int | None, int | None, int | None, int | None]`: returns `(header_row, name_col, phone_col, section_col)`.
  - `parse_contacts(grid, header_row: int | None, name_col: int, phone_col: int, section_col: int | None = None) -> list[ContactRow]`: skips fully blank lines.
  - `diff_contacts(conn, rows: list[ContactRow]) -> ContactDiff`
  - `apply_contact_diff(conn, diff: ContactDiff, filename: str, file_hash: str) -> None`
  - `add_student(conn, name: str, phone_raw: str, section: str | None = None) -> int`: `ValueError` on an invalid number.
  - `update_student(conn, student_id: int, **fields) -> None`
    - allowed fields: `name`, `phone` (raw text, normalised; `ValueError(problem)` if invalid), `stud_id` (`None` unlinks; `ValueError("ID already linked to <name>")`), `name_in_marks`, `section`, `active`, `notes`
    - updates `name_key` and `updated_at`
    - audits `"student_updated"` with the field names and old/new phone
  - `list_students(conn, include_inactive: bool = False) -> list[sqlite3.Row]`
  - `shared_number_groups(conn) -> list[list[sqlite3.Row]]`: active students only.
  - helper `tests/helpers.seed_contacts(conn, tmp_path) -> dict[str, int]`: imports `builders.CONTACTS` and returns name → id.

**Rules:**
- Header detection: name column = a cell containing `NAME` or `STUDENT`. Phone column = a cell containing `WHATSAPP`, `MOBILE`, `PHONE`, `CONTACT` or `NUMBER`. Section column = `SEC` or `SECTION`.
- A file row matches a saved student only when its `name_key` equals the `name_key` of exactly one saved student.
- Rows with no name → `invalid`.
- Same `name_key` twice in the file, or a key that matches more than one saved student → `duplicate_names`. These rows are not applied.
- Invalid numbers:
  - new students are inserted with `phone NULL` and `phone_raw` kept, and listed in `bad_numbers`
  - an existing valid phone is never overwritten by an invalid one
- `missing` = active saved students absent from the file. On apply they are set `active = 0`, never deleted.

- [ ] **Step 1: Write the failing tests**

```python
def test_first_import(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    s = {r["name"]: r for r in list_students(conn)}
    assert s["Gorantla Sai Kartik"]["phone"] == "+919876543202"
    assert s["Syed Afreen"]["phone"] == "+919876543208"
    assert s["Kolluri Anjali"]["phone"] is None and s["Kolluri Anjali"]["phone_raw"] == "98765432"
    assert [len(g) for g in shared_number_groups(conn)] == [2]

def test_reimport_changes(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Syed Afreen"], stud_id="100000008")
    rows = [ContactRow(1, "SYED AFREEN", normalise_phone("9876543299"), ""),        # reordered/caps, new phone
            ContactRow(2, "New Student", normalise_phone("9876543300"), "")]
    d = diff_contacts(conn, rows)
    assert [r.name for r in d.new] == ["New Student"]
    assert d.phone_changed[0][0] == ids["Syed Afreen"]
    assert len(d.missing) == 7
    apply_contact_diff(conn, d, "c.xlsx", "h")
    afreen = conn.execute("select * from students where id=?", (ids["Syed Afreen"],)).fetchone()
    assert afreen["stud_id"] == "100000008" and afreen["phone"] == "+919876543299"
    assert conn.execute("select count(*) from students where active=0").fetchone()[0] == 7
    assert conn.execute("select count(*) from students").fetchone()[0] == 9   # nothing deleted

def test_duplicate_names_not_applied(conn):
    rows = [ContactRow(1, "Syed Afreen", normalise_phone("9876543208"), ""),
            ContactRow(2, "AFREEN SYED", normalise_phone("9876543209"), "")]
    d = diff_contacts(conn, rows)
    assert len(d.duplicate_names) == 1 and d.new == []

def test_update_student_guards(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Nakka Ravi Teja"], stud_id="100000005")
    with pytest.raises(ValueError): update_student(conn, ids["Nakka Ravi Kiran"], stud_id="100000005")
    with pytest.raises(ValueError): update_student(conn, ids["Nakka Ravi Kiran"], phone="123")
    assert any(r["action"] == "student_updated" for r in audit.recent(conn))
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `contacts.py` and `tests/helpers.seed_contacts`.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/contacts.py tests/helpers.py tests/test_contacts.py
git commit -m "feat: contact list import, diff, apply and edits"
```

---

### Task 10: Matching engine (pure)

**Files:**
- Create: `marksapp/matching.py`
- Test: `tests/test_matching.py`

**Interfaces:**
- Consumes: `name_key`, `similarity` (Task 3).
- Produces:
  - `StudentRef(id: int, name: str, stud_id: str | None, name_in_marks: str | None, active: bool)`
  - `RowRef(exam_id: int, row_no: int, stud_id: str, name: str)`
  - `Candidate(student_id: int, name: str, score: float)`
  - `MatchResult`:
    - `stud_id: str`, `names: list[str]`, `rows: list[RowRef]`
    - `status: Literal["linked","proposed","review","not_found","ignored"]`
    - `student_id: int | None`, `candidates: list[Candidate]`, `reasons: list[str]`
  - `CANDIDATE_FLOOR = 70.0`, `CROSSCHECK_MIN = 85.0`, `MAX_CANDIDATES = 3`
  - `match_rows(rows: list[RowRef], students: list[StudentRef], ignored: set[str]) -> list[MatchResult]`: in order of first appearance.

**Algorithm:**

1. Group the rows by `stud_id`. `names` = the distinct names in the group.
2. **Group reasons:**
   - two rows with the same `exam_id` → `"Appears more than once in the same file"`
3. **`stud_id` linked to student S:**
   - `status = "linked"`, `student_id = S.id`
   - Cross-check each name: `max(similarity(n, S.name), similarity(n, S.name_in_marks or ""))`. If it is below `CROSSCHECK_MIN` → reason `f"Name in file differs from saved name ({S.name})"`, and `candidates = [S]`.
   - S inactive → reason `"Student is marked inactive"`.
   - Any reason → `status = "review"`, keeping `student_id`.
4. **`stud_id` in `ignored`** → `"ignored"`.
5. **Otherwise**, look in the pool of active students with `stud_id is None`:
   - `exact` = pool students with `name_key == name_key(names[0])`.
   - Group reasons, or more than one distinct `name_key` in `names` (reason `"Different names for the same ID across files"`) → `"review"`, with candidates from `exact` plus fuzzy.
   - Exactly one in `exact`, and no other unlinked group in this batch has the same key → `"proposed"`, with `student_id` and `candidates = [Candidate(.., 100)]`.
   - More than one in `exact` → `"review"`: `"Several students on your list have this name"`.
   - Exactly one in `exact`, but another group shares the key → `"review"`: `"Another student in the file has the same name"`.
   - Otherwise, fuzzy candidates scoring at least `CANDIDATE_FLOOR`, best `MAX_CANDIDATES` → `"review"`: `"Name not exactly on your list — pick the right student"`. With no candidates → `"not_found"`.
6. **Safety post-pass:** any `student_id` held by more than one `proposed` or `linked` result → all of those become `"review"`: `"Matches more than one student in the file"`.

- [ ] **Step 1: Write the failing tests**

```python
def S(id, name, stud_id=None, alt=None, active=True): return StudentRef(id, name, stud_id, alt, active)
def R(stud_id, name, exam=1, row=1): return RowRef(exam, row, stud_id, name)

def test_exact_reordered_name_is_proposed():
    [m] = match_rows([R("1", "PALLAPU MEGHANA SRI")], [S(10, "Meghana Sri Pallapu")], set())
    assert (m.status, m.student_id) == ("proposed", 10)

def test_linked_by_id_ignores_format():
    [m] = match_rows([R("1", "PALLAPU MEGHANA SRI")], [S(10, "Meghana Sri Pallapu", "1")], set())
    assert (m.status, m.reasons) == ("linked", [])

def test_linked_name_differs_needs_review():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(10, "Meghana Sri Pallapu", "1")], set())
    assert m.status == "review" and m.student_id == 10 and "differs" in m.reasons[0]

def test_name_in_marks_satisfies_crosscheck():
    [m] = match_rows([R("1", "PALLAPU MEGHANA SRI")], [S(10, "Meghana", "1", alt="PALLAPU MEGHANA SRI")], set())
    assert m.status == "linked"

def test_fuzzy_never_proposed():
    [m] = match_rows([R("2", "GORANTLA SAI KARTHIK")], [S(11, "Gorantla Sai Kartik")], set())
    assert m.status == "review" and m.candidates[0].student_id == 11

def test_near_identical_different_names_are_never_proposed():
    [m] = match_rows([R("7", "KOLLURI ANJANI")], [S(12, "Kolluri Anjali")], set())
    assert m.status == "review"

def test_sibling_not_a_candidate():
    [m] = match_rows([R("6", "NAKKA RAVI KIRAN")], [S(13, "Nakka Ravi Teja")], set())
    assert m.status == "not_found" and m.candidates == []

def test_two_list_students_same_name():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(1, "Syed Afreen"), S(2, "AFREEN SYED")], set())
    assert m.status == "review" and {c.student_id for c in m.candidates} == {1, 2}

def test_two_file_rows_same_name():
    ms = match_rows([R("1", "SYED AFREEN", row=1), R("9", "SYED AFREEN", row=2)], [S(1, "Syed Afreen")], set())
    assert [m.status for m in ms] == ["review", "review"]

def test_same_id_across_exams_grouped():
    [m] = match_rows([R("1", "SYED AFREEN", exam=1), R("1", "SYED AFREEN", exam=2)], [S(1, "Syed Afreen", "1")], set())
    assert m.status == "linked" and len(m.rows) == 2

def test_different_names_same_unlinked_id():
    [m] = match_rows([R("1", "SYED AFREEN", exam=1), R("1", "NAKKA RAVI TEJA", exam=2)], [S(1, "Syed Afreen")], set())
    assert m.status == "review"

def test_duplicate_in_same_file():
    [m] = match_rows([R("1", "SYED AFREEN", row=1), R("1", "SYED AFREEN", row=2)], [S(1, "Syed Afreen", "1")], set())
    assert m.status == "review"

def test_inactive_linked():
    [m] = match_rows([R("1", "SYED AFREEN")], [S(1, "Syed Afreen", "1", active=False)], set())
    assert m.status == "review"

def test_ignored_and_not_found():
    ms = match_rows([R("5", "X Y"), R("6", "Q R")], [], {"5"})
    assert [m.status for m in ms] == ["ignored", "not_found"]

def test_linked_student_not_offered_to_new_id():
    [m] = match_rows([R("99", "SYED AFREEN")], [S(1, "Syed Afreen", "1")], set())
    assert m.status == "not_found"

def test_one_student_never_holds_two_results():
    students = [S(1, "Syed Afreen"), S(2, "Nakka Ravi Teja", "5")]
    rows = [R("1", "SYED AFREEN"), R("5", "NAKKA RAVI TEJA"), R("8", "AFREEN SYED", row=3)]
    held = [m.student_id for m in match_rows(rows, students, set()) if m.status in ("proposed", "linked")]
    assert len(held) == len(set(held))
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `matching.py` to the algorithm above.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/matching.py tests/test_matching.py
git commit -m "feat: student matching engine with safe linking rules"
```

---

### Task 11: Rounds, exams and links storage

**Files:**
- Create: `marksapp/rounds.py`
- Modify: `tests/helpers.py`
- Test: `tests/test_rounds.py`

**Interfaces:**
- Consumes: `ParsedMarksFile`, `MarksRow` (Task 7); `ExamName` (Task 8); `match_rows`, `StudentRef`, `RowRef`, `MatchResult` (Task 10); `decode_mark` (Task 1).
- Produces:
  - `class RoundLocked(Exception)`
  - `LOCKING_STATES = {"sent", "accepted", "sending", "unknown"}`
  - `ExamRec`: `id`, `round_id`, `display_name`, `exam_type`, `exam_number: int | None`, `sort_order`, `test_name`, `test_date`, `maxes: dict[str, float | None]`, `filename`, `file_hash`, `via_ocr: bool`
  - `MarkRowRec`: `id`, `exam_id`, `row_no`, `stud_id`, `name_in_file`, `section`, `maths: Mark`, `physics: Mark`, `chemistry: Mark`, `total_in_file: Mark`, `total_choice: str | None`, `edited: bool`
  - `create_round(conn, label: str) -> int`
  - `list_rounds(conn) -> list[sqlite3.Row]`: newest first.
  - `round_locked(conn, round_id: int) -> bool`
  - `find_duplicate_exam(conn, file_hash: str, test_name: str | None, test_date: str | None) -> sqlite3.Row | None`
  - `add_exam(conn, round_id: int, parsed: ParsedMarksFile, name: ExamName, filename: str, file_hash: str, via_ocr: bool = False, replace_exam_id: int | None = None) -> int`
    - raises `RoundLocked` if the round (or the replaced exam's round) is locked
    - deletes the round's message rows whose status is not in `LOCKING_STATES`
    - inserts the marks and unreadable rows
    - audits `"exam_added"`
  - `remove_exam(conn, exam_id: int) -> None`: same lock and clearing rules; audited.
  - `list_exams(conn, round_id) -> list[ExamRec]`: ordered by `sort_order`, `exam_number`, `id`.
  - `round_rows(conn, round_id) -> list[tuple[ExamRec, MarkRowRec]]`
  - `round_warnings(conn, round_id) -> list[str]`
  - `match_round(conn, round_id) -> list[MatchResult]`
  - `confirm_links(conn, links: list[tuple[str, int, str]]) -> None`
    - each tuple is `(stud_id, student_id, name_in_file)`; it sets `stud_id` and `name_in_marks`
    - all-or-nothing; `ValueError` if a student already has a different `stud_id`, the `stud_id` is held by another student, or the list repeats a `stud_id` or student
    - audits `"link_confirmed"` per link
  - `accept_name(conn, student_id: int, name_in_file: str) -> None`: sets `name_in_marks`; audited.
  - `ignore_ids(conn, items: list[tuple[str, str]]) -> None`
  - `unignore_id(conn, stud_id: str) -> None`
  - `save_layout(conn, signature: str, column_map: dict[str, int]) -> None`
  - `get_layout(conn, signature: str) -> dict[str, int] | None`
  - helper `tests/helpers.seed_round(conn, tmp_path, fmt="xlsx", mains=True) -> int`: creates a round, then adds the Advance-4 fixture and (optionally) the Mains-4 fixture with names from `suggest_exam_name`.

`round_warnings`: if the numbered exams in the round have different numbers → `"Exam numbers differ in this round: Advance Exam - 5, Mains Exam - 4"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_add_and_order(conn, tmp_path):
    rid = seed_round(conn, tmp_path)                     # helper adds Advance then Mains
    assert [e.display_name for e in list_exams(conn, rid)] == ["Advance Exam - 4", "Mains Exam - 4"]
    assert len(round_rows(conn, rid)) == 16

def test_duplicate_detection(conn, tmp_path):
    rid = seed_round(conn, tmp_path, mains=False); e = list_exams(conn, rid)[0]
    assert find_duplicate_exam(conn, e.file_hash, None, None)["id"] == e.id
    assert find_duplicate_exam(conn, "other", "JEE(Adv)/WTA-4", "17-August-2026")["id"] == e.id

def test_locked_after_send(conn, tmp_path):
    seed_contacts(conn, tmp_path); rid = seed_round(conn, tmp_path, mains=False)
    sid = conn.execute("select id from students limit 1").fetchone()[0]
    conn.execute("insert into messages(round_id,student_id,phone,body,body_hash,status) values (?,?,?,?,?,?)",
                 (rid, sid, "+91", "b", "h", "sent"))
    assert round_locked(conn, rid)
    with pytest.raises(RoundLocked): remove_exam(conn, list_exams(conn, rid)[0].id)

def test_adding_file_clears_approvals(conn, tmp_path): ...  # insert an 'approved' row, add Mains, row gone

def test_confirm_links_all_or_nothing(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    with pytest.raises(ValueError):
        confirm_links(conn, [("1", ids["Syed Afreen"], "SYED AFREEN"), ("2", ids["Syed Afreen"], "X")])
    assert conn.execute("select count(*) from students where stud_id is not null").fetchone()[0] == 0

def test_links_carry_to_next_round(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path); r1 = seed_round(conn, tmp_path)
    proposed = [m for m in match_round(conn, r1) if m.status == "proposed"]
    confirm_links(conn, [(m.stud_id, m.student_id, m.names[0]) for m in proposed])
    r2 = seed_round(conn, tmp_path)
    by_id = {m.stud_id: m for m in match_round(conn, r2)}
    assert all(by_id[m.stud_id].status == "linked" for m in proposed)

def test_ignore(conn, tmp_path):
    rid = seed_round(conn, tmp_path, mains=False); ignore_ids(conn, [("100000001", "PALLAPU MEGHANA SRI")])
    assert {m.stud_id: m.status for m in match_round(conn, rid)}["100000001"] == "ignored"

def test_layout_roundtrip(conn):
    save_layout(conn, "sig", {"stud_id": 0}); assert get_layout(conn, "sig") == {"stud_id": 0}

def test_round_warns_when_exam_numbers_differ(conn, tmp_path):
    rid = seed_round(conn, tmp_path, mains=False)      # Advance 4
    # add a Mains-5 fixture via add_exam
    assert round_warnings(conn, rid) == ["Exam numbers differ in this round: Advance Exam - 4, Mains Exam - 5"]
```

For `test_adding_file_clears_approvals`: insert an `approved` message row, add the Mains file, and assert the row no longer exists.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `rounds.py` and the `seed_round` helper.**

All writes run inside `with conn:` transactions.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/rounds.py tests/helpers.py tests/test_rounds.py
git commit -m "feat: rounds, exams, link confirmation and layouts storage"
```

---

### Task 12: Per-student results and issues

**Files:**
- Create: `marksapp/results.py`
- Test: `tests/test_results.py`

**Interfaces:**
- Consumes: everything in Task 11; `Mark` (Task 1).
- Produces:
  - `Issue(code: str, text: str, blocking: bool)`
  - `ExamMarks`:
    - exam: `exam_id`, `display_name`, `exam_type`, `exam_number`
    - row: `mark_row_id: int | None`
    - marks: `maths`, `physics`, `chemistry`, `total`, `total_in_file`, `computed_total` (all `Mark`)
    - `absent_row: bool`, `issues: list[Issue]`
  - `StudentResult`:
    - fields: `student_id`, `name`, `phone: str | None`, `stud_id`, `exams: list[ExamMarks]`, `issues: list[Issue]` (student-level plus every exam-level issue)
    - properties: `status -> "ready" | "review"`, `blocking -> bool`
  - `RoundResults`:
    - `students: list[StudentResult]`
    - `links_to_confirm: list[MatchResult]` (proposed, plus review results with an unlinked `stud_id`)
    - `not_found: list[MatchResult]`, `ignored: list[MatchResult]`
    - `not_in_any_file: list[sqlite3.Row]`, `unreadable: list[sqlite3.Row]`
  - `compute_exam_marks(exam: ExamRec, row: MarkRowRec | None) -> ExamMarks`: pure.
  - `build_results(conn, round_id: int) -> RoundResults`
  - `set_total_choice(conn, mark_row_id: int, choice: Literal["file", "sum"]) -> None`: audited.
  - `edit_mark(conn, mark_row_id: int, field: Literal["maths","physics","chemistry","total_in_file"], raw: str) -> None`: `parse_mark`, sets `edited = 1`, audits old and new values.

**Issue codes and texts:**

| code | text | blocking |
|---|---|---|
| `absent` | `Absent from {exam}? Confirm before sending` | no |
| `subject_missing` | `{Subject} mark missing in {exam} (shown as NA)` | no |
| `subject_absent` | `{Subject} marked AB in {exam}` | no |
| `out_of_range` | `{Subject} {value} is outside the allowed range in {exam} (max {max})` | yes |
| `total_over_max` | `Total {value} is above the maximum {max} in {exam}` | yes |
| `total_mismatch` | `Total in file ({file}) does not match sum of subjects ({sum}) in {exam} — choose one` | yes |
| `no_phone` | `No valid WhatsApp number` | yes |
| `ocr` | `Read from a scanned PDF — check every mark against the file` | no |
| `match` | each reason from a linked student's review `MatchResult` | yes |
| `inactive` | `Student is marked inactive — reactivate in Contacts to send` | yes |

**`compute_exam_marks` rules:**
- `row is None` → all subjects AB, total AB, `absent_row = True`, `absent` issue.
- Range check: valid when `-max ≤ value ≤ max` (skipped when max is `None`).
- All three subjects numeric → `computed_total` = their sum, then:
  - `total_choice == "file"` → total = file value
  - `total_choice == "sum"` → total = sum
  - otherwise: if the file total is numeric and differs → `total_mismatch`, total = sum; else total = sum.
- Any subject NA → total NA, plus `subject_missing`.
- All three AB (row present) → total AB, plus `absent`.
- Some AB and some numeric → `subject_absent`, and total NA.

**`build_results` rules:**
- A result is made for every student with `stud_id` set who is active, or who appears in this round's files.
- Each exam's row is taken by `stud_id`. The `match` and `inactive` issues come from that student's `MatchResult`. `no_phone` is added when `phone` is `None`. `ocr` is added for `via_ocr` exams that have a row.
- `not_in_any_file` = active students with `stud_id` `None` who are not `student_id` or a candidate in any `links_to_confirm` entry.

- [ ] **Step 1: Write the failing tests**

```python
def exam(maxes=(60, 60, 60, 180)): ...   # ExamRec factory, Advance Exam - 4
def row(m, p, c, t, choice=None): ...    # MarkRowRec factory using parse_mark

def test_normal_and_negative():
    em = compute_exam_marks(exam(), row(23, 16, -7, 32))
    assert em.total == Mark("num", 32.0) and em.issues == []

def test_absent_row():
    em = compute_exam_marks(exam(), None)
    assert em.absent_row and em.total == AB and [i.code for i in em.issues] == ["absent"]

def test_total_mismatch_blocks_until_chosen():
    em = compute_exam_marks(exam(), row(41, 32, 17, 91))
    assert [(i.code, i.blocking) for i in em.issues] == [("total_mismatch", True)]
    assert compute_exam_marks(exam(), row(41, 32, 17, 91, "file")).total == Mark("num", 91.0)
    assert compute_exam_marks(exam(), row(41, 32, 17, 91, "sum")).issues == []

def test_missing_subject_is_na_not_zero():
    em = compute_exam_marks(exam(), row(41, None, 17, 90))
    assert em.physics == NA and em.total == NA and em.issues[0].code == "subject_missing"

def test_out_of_range():
    assert compute_exam_marks(exam(), row(75, 1, 1, 77)).issues[0].code == "out_of_range"
    assert compute_exam_marks(exam(), row(-61, 1, 1, -59)).issues[0].code == "out_of_range"

def test_build_round_one_then_linked(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path); rid = seed_round(conn, tmp_path)
    rr = build_results(conn, rid)
    assert rr.students == [] and len(rr.links_to_confirm) >= 5
    confirm_links(conn, [(m.stud_id, m.student_id, m.names[0]) for m in rr.links_to_confirm if m.status == "proposed"])
    rr = build_results(conn, rid)
    afreen = next(s for s in rr.students if s.name == "Syed Afreen")
    assert afreen.status == "ready" and [e.total.display() for e in afreen.exams] == ["25", "60"]
    anjali = [s for s in rr.students if s.name == "Kolluri Anjali"]
    assert not anjali or anjali[0].blocking                         # bad number → no_phone

def test_linked_student_absent_from_all(conn, tmp_path): ...   # link a contact to an ID not in files → 2 absent issues
def test_ocr_exam_flags_every_row(conn, tmp_path): ...         # add_exam(via_ocr=True) → every result has "ocr"
def test_not_in_any_file_excludes_candidates(conn, tmp_path): ...
def test_round_two_clean_after_short_contact_name(conn, tmp_path):
    # contact "Meghana" (short); round 1: review → owner picks → confirm_links;
    # round 2: status linked, no match issue
```

- `test_linked_student_absent_from_all`: link a contact to an ID that isn't in the files. Assert it gets 2 `absent` issues.
- `test_ocr_exam_flags_every_row`: `add_exam(via_ocr=True)`. Assert every result has an `ocr` issue.
- `test_round_two_clean_after_short_contact_name`: save a contact as "Meghana" (short). In round 1 its row needs review; the owner picks the student and `confirm_links` saves it. In round 2 the status is `linked`, with no `match` issue.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `results.py`.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/results.py tests/test_results.py
git commit -m "feat: per-student results, issues, total choice and mark edits"
```

---

### Task 13: Message rendering and outbox

**Files:**
- Create: `marksapp/messages.py`, `marksapp/outbox.py`
- Test: `tests/test_messages.py`, `tests/test_outbox.py`

**Interfaces:**
- Consumes: `StudentResult`, `build_results` (Task 12); `get_setting` (Task 5); `title_name` (Task 3).
- Produces (`messages.py`):
  - `MessageSettings(exam_block: str, separator: str, include_name: bool, name_line: str)`
  - `message_settings(conn) -> MessageSettings`
  - `render_message(result: StudentResult, ms: MessageSettings) -> str`
  - `content_hash(phone: str, body: str) -> str`: sha256 of `f"{phone}\n{body}"`.
- Produces (`outbox.py`):
  - `OutboxRec`: dataclass mirroring the `messages` row.
  - `approve(conn, round_id: int, results: list[StudentResult], ms: MessageSettings, *, allow_review: bool = False) -> list[int]`
    - returns the approved student ids
    - skips any blocking result, any non-ready result unless `allow_review`, and any student whose row is in `LOCKING_STATES`
    - upserts `status = "approved"`, `body`, `body_hash`, `phone`, `approved_at`
    - audits `"approved"`
  - `skip(conn, round_id: int, student_ids: list[int]) -> None`
  - `get_outbox(conn, round_id: int) -> dict[int, OutboxRec]`: keyed by `student_id`.
  - `check_current(conn, rec: OutboxRec, result: StudentResult | None, ms: MessageSettings) -> bool`: if the result is `None`, blocking, or `content_hash(result.phone, render_message(...)) != rec.body_hash` → deletes the row, audits `"approval_cleared_changed"` and returns `False`.
  - `mark_sent(conn, message_id, method: str = "phone") -> None`
  - `mark_failed(conn, message_id, error: str) -> None`
  - `mark_sending(conn, message_id) -> None`
  - `mark_accepted(conn, message_id, api_message_id: str) -> None`
  - `mark_unknown(conn, message_id, error: str) -> None`
  - `reset_for_resend(conn, message_id) -> None`: sent/accepted/unknown → approved; audited `"resend_requested"`.
  - `recover_interrupted(conn) -> int`: sending → unknown.
  - `phone_link(phone_e164: str, body: str, kind: str) -> str`

**Allowed transitions** (anything else raises `ValueError(f"Cannot go from {old} to {new}")`):
- `approved` → `sent`, `failed`, `sending`, `skipped`
- `failed` → `sent`, `failed`, `sending`, `skipped`
- `sending` → `accepted`, `failed`, `unknown`
- `skipped` → `approved` (only through `approve`)

`mark_sent`, `mark_sending` and `mark_failed` increment `attempts`. Every transition is audited.

**`phone_link`:**
- `wa.me` → `https://wa.me/{digits}?text={quote(body, safe='')}`
- `web` → `https://web.whatsapp.com/send?phone={digits}&text=...`
- `desktop` → `whatsapp://send?phone={digits}&text=...`

- [ ] **Step 1: Write the failing tests**

```python
SPEC_BODY = ("*Advance Exam - 4 Marks*\n\nMaths - 41\nPhysics - 32\nChemistry - 17\n\n*Total Marks - 90*"
             "\n\n*Mains Exam - 4 Marks*\n\nMaths - 62\nPhysics - 17\nChemistry - 16\n\n*Total Marks - 95*")

def test_render_exact_spec_format(): ...      # StudentResult with those values → render == SPEC_BODY
def test_render_with_name(): ...              # include_name → body.startswith("*Pallapu Meghana Sri*\n\n*Advance")
def test_render_ab_na_negative(): ...         # "Chemistry - -7", "Maths - AB", "Total Marks - NA"
def test_hash_changes_with_phone():
    assert content_hash("+919876543201", "b") != content_hash("+919876543202", "b")

def test_approve_only_ready(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)                     # helper: seed + confirm proposed
    ms = message_settings(conn)
    approved = approve(conn, rid, rr.students, ms)
    assert set(approved) == {s.student_id for s in rr.students if s.status == "ready"}
    blocked = [s for s in rr.students if s.blocking]
    assert approve(conn, rid, blocked, ms, allow_review=True) == []

def test_change_after_approval_clears(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path); ms = message_settings(conn)
    s = next(x for x in rr.students if x.status == "ready"); approve(conn, rid, [s], ms)
    update_student(conn, s.student_id, phone="9000000001")
    fresh = next(x for x in build_results(conn, rid).students if x.student_id == s.student_id)
    rec = get_outbox(conn, rid)[s.student_id]
    assert check_current(conn, rec, fresh, ms) is False and s.student_id not in get_outbox(conn, rid)

def test_mark_sent_twice_raises(conn, tmp_path): ...          # second mark_sent → ValueError
def test_resend_requires_reset(conn, tmp_path): ...           # sent → reset_for_resend → approved → mark_sent ok
def test_recover_interrupted(conn, tmp_path): ...             # 'sending' → 'unknown'
def test_approve_never_touches_sent(conn, tmp_path): ...

def test_phone_link():
    assert phone_link("+919876543201", "*A*\nB", "wa.me") == "https://wa.me/919876543201?text=%2AA%2A%0AB"
    assert phone_link("+919876543201", "x", "web").startswith("https://web.whatsapp.com/send?phone=919876543201&text=")
```

- `test_render_exact_spec_format`: a `StudentResult` with those values renders exactly `SPEC_BODY`.
- `test_render_with_name`: with `include_name`, the body starts with `"*Pallapu Meghana Sri*\n\n*Advance"`.
- `test_render_ab_na_negative`: output contains `"Chemistry - -7"`, `"Maths - AB"` and `"Total Marks - NA"`.
- `test_mark_sent_twice_raises`: a second `mark_sent` raises `ValueError`.
- `test_resend_requires_reset`: sent → `reset_for_resend` → approved → `mark_sent` works.
- `test_recover_interrupted`: a `sending` row becomes `unknown`.
- `test_approve_never_touches_sent`: approving a round again leaves `sent` rows unchanged.

Add `linked_round(conn, tmp_path) -> tuple[int, RoundResults]` to `tests/helpers.py`.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `messages.py` and `outbox.py`.**

`render_message`:
- Optionally starts with `name_line.format(name=title_name(name))` plus the separator.
- Then the exam blocks, each `exam_block.format(exam=display_name, maths=..display(), physics=.., chemistry=.., total=..)`, joined by the separator.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/messages.py marksapp/outbox.py tests/test_messages.py tests/test_outbox.py tests/helpers.py
git commit -m "feat: message rendering, approvals and send-state machine"
```

---

### Task 14: Reports and history

**Files:**
- Create: `marksapp/reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: `build_results` (Task 12); `get_outbox` (Task 13).
- Produces:
  - `STATUS_LABELS = {"approved": "Pending", "failed": "Failed", "sending": "Sending", "unknown": "Unknown — check", "sent": "Sent", "accepted": "Sent", "skipped": "Skipped"}`. A student with no row is `"Pending"`.
  - `round_report(conn, round_id) -> pandas.DataFrame`
    - columns `["Student", "WhatsApp", "Status", "Method", "Sent at", "Attempts", "Error"]`
    - one row per `StudentResult`
  - `round_counts(conn, round_id) -> dict[str, int]`: keys `Sent`, `Failed`, `Pending`, `Skipped`, `Unknown — check`.
  - `report_xlsx(df: pandas.DataFrame) -> bytes`
  - `student_history(conn, student_id) -> pandas.DataFrame`
    - columns `["Round", "Exam", "Test date", "Maths", "Physics", "Chemistry", "Total"]`, newest round first
    - values via `Mark.display()`, from rows matched by the student's `stud_id`
  - `message_log(conn, student_id) -> pandas.DataFrame`
    - columns `["Round", "Status", "WhatsApp", "Method", "Sent at", "Message"]`

- [ ] **Step 1: Write the failing tests**

```python
def test_counts_and_report(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path); ms = message_settings(conn)
    ids = approve(conn, rid, rr.students, ms); out = get_outbox(conn, rid)
    mark_sent(conn, out[ids[0]].id); mark_failed(conn, out[ids[1]].id, "Number not on WhatsApp")
    c = round_counts(conn, rid)
    assert c["Sent"] == 1 and c["Failed"] == 1 and c["Pending"] == len(rr.students) - 2
    df = round_report(conn, rid)
    assert list(df.columns) == ["Student", "WhatsApp", "Status", "Method", "Sent at", "Attempts", "Error"]
    assert openpyxl.load_workbook(io.BytesIO(report_xlsx(df))).active.max_row == len(df) + 1

def test_history(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    s = next(x for x in rr.students if x.name == "Muddana Venkata Sai Srinivas Rao")
    h = student_history(conn, s.student_id)
    assert list(h["Exam"]) == ["Advance Exam - 4", "Mains Exam - 4"] and h.iloc[0]["Chemistry"] == "-7"
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `reports.py`.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/reports.py tests/test_reports.py
git commit -m "feat: delivery report, Excel export and student history"
```

---

### Task 15: App shell, login and Contacts page

**Files:**
- Create: `app.py`, `.streamlit/config.toml`, `marksapp/ui/__init__.py`, `marksapp/ui/common.py`, `marksapp/ui/contacts_page.py`, and a stub `render(conn)` that writes "Coming soon" for each of `round_page`, `attention_page`, `preview_page`, `send_page`, `reports_page`, `settings_page`.
- Test: `tests/test_ui_shell.py`

**Interfaces:**
- Consumes: Tasks 4, 5, 9, 13 (`recover_interrupted`).
- Produces:
  - `common.get_conn() -> sqlite3.Connection`: one per Streamlit session, cached in `st.session_state["conn"]`. `connect()` is called with `check_same_thread=False`.
  - `common.login_gate(conn) -> bool`: shows set-password or login forms; `True` when logged in (`st.session_state["logged_in"]`).
  - `common.pick_round(conn, key: str) -> int | None`: selectbox of rounds, newest first.
  - Each page module exposes `render(conn) -> None`.
  - Widget keys used by tests: `new_pw`, `new_pw2`, `set_pw`, `login_pw`, `login_btn`.
  - conftest fixture `app_env(tmp_path, monkeypatch)`: sets `MARKSAPP_DATA_DIR` to the same `tmp_path` that `conn` uses, so the app and the test share one database.

**`app.py`:**
1. `st.set_page_config(page_title="Marks to Parents", layout="wide")`
2. `conn = get_conn()`
3. Once per session, `recover_interrupted(conn)`.
4. `if not login_gate(conn): st.stop()`
5. `st.navigation` with pages in this order: Contacts, New round, Needs attention, Preview & approve, Send, Reports & history, Settings. Each page is `st.Page(lambda: module.render(conn), title=..., url_path=...)`.

`config.toml`:

```toml
[server]
address = "127.0.0.1"
[browser]
gatherUsageStats = false
```

**Contacts page:**
1. `file_uploader` (`xlsx`, `xls`, `csv`, `pdf`) → `load_grid`.
2. Column selectboxes, pre-filled by `detect_contact_columns`.
3. A preview of the first 5 parsed rows.
4. A summary from `diff_contacts`: counts plus expanders for new, changed numbers, will become inactive, duplicate names (not applied), invalid rows, bad numbers, and shared numbers.
5. **Apply changes** → `apply_contact_diff`.

Below that:
- A searchable `st.dataframe` of students: name, number (`pretty_phone`), STUD_ID, section, active.
- An edit form for the selected student, calling `update_student` and showing any `ValueError` text with `st.error`.
- An **Add student** form.
- When `shared_number_groups` is non-empty, a warning: "Some parents have more than one child on the list. Turn on 'Start each message with the student's name' in Settings so they can tell the messages apart."

- [ ] **Step 1: Write the failing tests**

Use `streamlit.testing.v1.AppTest.from_function`. The function imports `marksapp` inside itself and uses `MARKSAPP_DATA_DIR` set by a fixture.

```python
def test_first_run_asks_for_password(app_env):
    at = AppTest.from_function(gate_script).run()
    assert "Set a password" in [h.value for h in at.subheader]
    at.text_input(key="new_pw").input("correct horse"); at.text_input(key="new_pw2").input("correct horse")
    at.button(key="set_pw").click().run()
    assert at.session_state["logged_in"] is True

def test_wrong_password_rejected(app_env): ...   # pre-set password; login with wrong → error shown, not logged in

def test_contacts_page_renders_and_warns_siblings(app_env, conn, tmp_path):
    seed_contacts(conn, tmp_path)
    at = AppTest.from_function(contacts_script).run()
    assert not at.exception and any("more than one child" in w.value for w in at.warning)
```

`test_wrong_password_rejected`: with a password already set, a login with the wrong password shows an error and does not log in.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement the shell, `common.py`, the Contacts page and the stubs.**

- [ ] **Step 4: Run tests — expect PASS.**

Then run `pytest -q`. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app.py .streamlit marksapp/ui tests/test_ui_shell.py
git commit -m "feat: Streamlit shell with password login and Contacts page"
```

---

### Task 16: New round and Needs attention pages

**Files:**
- Modify: `marksapp/ui/round_page.py`, `marksapp/ui/attention_page.py`
- Test: `tests/test_ui_round.py`

**Interfaces:**
- Consumes: Tasks 6–12.
- Produces: `round_page.render(conn)`, `attention_page.render(conn)`, and `round_page.prepare_upload(conn, data: bytes, filename: str, column_map: dict | None) -> UploadPreview`.
  - `prepare_upload` is pure apart from reading saved layouts, and is what makes uploads unit-testable.
  - `UploadPreview(parsed: ParsedMarksFile | None, name: ExamName | None, duplicate: sqlite3.Row | None, error: str | None, via_ocr: bool)`

**New round page:**
1. Choose **Start new round** (label defaults to `f"Round of {date.today():%d-%b-%Y}"`) or an existing unlocked round.
2. Upload files (`accept_multiple_files=True`).
3. For each file, `prepare_upload` gives a preview showing:
   - the detected exam name, editable: exam type selectbox from the rules, number input, display text
   - test name, date, max marks
   - number of rows read, the first 5 rows, and any unreadable rows
4. If `missing_fields` is non-empty, show column selectboxes, re-parse with the chosen map, and on add call `save_layout`.
5. A duplicate shows a warning and a **Replace the earlier import** checkbox.
6. **Add to round** → `add_exam`. `RoundLocked` → `st.error("Messages from this round have already been sent. Start a new round for this file.")`.
7. Below: the round's exams with **Remove** buttons (disabled when locked), and `round_warnings` shown as `st.warning`.
8. `NoTextInPdf` → `error = "This PDF is a scanned image. Scanned PDFs need OCR (stage 2)."` (replaced in Task 19).

**Needs attention page** (`pick_round`, then `build_results` once per run):
1. **Confirm links** (`links_to_confirm`):
   - one row per entry with the file name, ID and section
   - proposed entries: a checkbox, ticked by default
   - review entries: a selectbox of candidates plus "Not on my list" and "Decide later", with the reasons shown
   - **Save links** (key `save_links`) → `confirm_links` for the ticked/picked entries and `ignore_ids` for "Not on my list", then `st.rerun()`
2. **Name differs from saved name**: linked students with `match` issues. **This is correct** → `accept_name`.
3. **Marks to check**: per student, its issues.
   - `total_mismatch` → radio "Use file total {x}" / "Use sum {y}" → `set_total_choice`.
   - Any other mark issue → number/AB/NA text inputs → `edit_mark`.
4. **Not found in your list** (`not_found`):
   - **Not my student** → `ignore_ids`
   - **Link to…** → a selectbox of active unlinked students → `confirm_links`
5. **On your list but not in any file**, **Not my students (N)** (collapsed, with **Undo** → `unignore_id`) and **Unreadable rows** (raw text).

- [ ] **Step 1: Write the failing tests**

```python
def test_prepare_upload_reads_sample(conn, marks_files):
    p = marks_files["pdf"]; up = prepare_upload(conn, p.read_bytes(), p.name, None)
    assert up.error is None and up.name.display == "Advance Exam - 4" and len(up.parsed.rows) == 8

def test_prepare_upload_flags_duplicate(conn, tmp_path, marks_files):
    seed_round(conn, tmp_path, mains=False); p = marks_files["xlsx"]
    assert prepare_upload(conn, p.read_bytes(), p.name, None).duplicate is not None

def test_prepare_upload_scanned_pdf(conn, tmp_path):
    p = tmp_path / "s.pdf"; builders.write_blank_pdf(p)
    assert "scanned" in prepare_upload(conn, p.read_bytes(), p.name, None).error

def test_attention_save_links(app_env, conn, tmp_path):
    seed_contacts(conn, tmp_path); rid = seed_round(conn, tmp_path)
    at = AppTest.from_function(attention_script).run()
    assert not at.exception
    at.button(key="save_links").click().run()
    assert conn.execute("select count(*) from students where stud_id is not null").fetchone()[0] >= 5
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement both pages.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/ui/round_page.py marksapp/ui/attention_page.py tests/test_ui_round.py
git commit -m "feat: New round upload and Needs attention review pages"
```

---

### Task 17: Preview & approve, Send (phone), Reports and Settings pages

**Files:**
- Modify: `marksapp/ui/preview_page.py`, `marksapp/ui/send_page.py`, `marksapp/ui/reports_page.py`, `marksapp/ui/settings_page.py`
- Test: `tests/test_ui_send.py`

**Interfaces:**
- Consumes: Tasks 5, 12, 13, 14.
- Produces: `render(conn)` for each page. `send_page.next_to_send(conn, round_id, only: set[int] | None) -> tuple[OutboxRec, StudentResult] | None`, which is the testable core of the guided flow.

**Preview & approve:**
- A table with columns Student, WhatsApp, one column per exam (total), and Status. Status is the outbox label when a row exists, otherwise Ready / Needs review.
- Rows can be selected (`st.dataframe(..., on_select="rerun", selection_mode="multi-row")`).
- Buttons:
  - **Approve all Ready ({n})** (key `approve_all`)
  - **Approve selected** (ready only)
  - **Skip selected**
- Detail selectbox:
  - shows the exact message in `st.code(body, language=None)`, plus the number and the issues
  - **Approve after checking** (`allow_review=True`, disabled when blocking)
  - **Skip**

**Send (phone mode):**
- Filter: All approved / Selected students (multiselect) / Failed only (retry).
- `next_to_send` first runs `check_current` over **every** `approved` and `failed` row in the round, so all stale approvals are dropped. It then returns the first remaining row in student-name order. The count of dropped rows is shown as "{n} messages changed since approval — re-approve them on Preview".
- The card shows: student name, `pretty_phone`, the message (`st.code`), `st.link_button("Open in WhatsApp", phone_link(...))`, then **✅ Sent** (key `mark_sent`, calls `mark_sent`), **Couldn't send** (`mark_failed` with a reason text input) and **Skip**.
- A progress line: "{sent} of {total} sent".
- Sent rows show "Already sent on {sent_at}" with a **Send again** button (`reset_for_resend`, behind a confirm checkbox).

**Reports & history:**
- `round_counts` as `st.metric`s, `round_report` as a table, and **Download Excel** (`report_xlsx`).
- A student picker showing `student_history` and `message_log`.
- An expander with `audit.recent`.

**Settings:**
- Change password.
- Message: an `exam_block` text area, the include-name checkbox and the name-line input, with a live preview from a made-up `StudentResult`. Format errors (`KeyError`/`ValueError` from `str.format`) → `st.error`, and nothing is saved.
- Exam rules: `st.data_editor` with columns Keyword and Exam type.
- Link kind radio: `wa.me` / WhatsApp Web / Desktop app.

- [ ] **Step 1: Write the failing tests**

```python
def test_next_to_send_skips_changed(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path); ms = message_settings(conn)
    ids = approve(conn, rid, rr.students, ms)
    update_student(conn, ids[0], phone="9000000001")              # first one now stale
    rec, res = next_to_send(conn, rid, None)
    assert rec.student_id != ids[0] and ids[0] not in get_outbox(conn, rid)

def test_next_to_send_none_when_all_sent(conn, tmp_path): ...

def test_preview_approve_all_ready(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    at = AppTest.from_function(preview_script).run()
    at.button(key="approve_all").click().run()
    assert len(get_outbox(conn, rid)) == sum(s.status == "ready" for s in rr.students)

def test_send_page_marks_sent(app_env, conn, tmp_path): ...   # approve, render send page, click "sent" → status sent
def test_settings_rejects_bad_template(app_env, conn): ...    # "{maths" → error, setting unchanged
```

- `test_next_to_send_none_when_all_sent`: once every approved message is sent, `next_to_send` returns `None`.
- `test_send_page_marks_sent`: approve, render the Send page and click **✅ Sent**. Assert the status is `sent`.
- `test_settings_rejects_bad_template`: `"{maths"` shows an error and the setting is unchanged.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement the four pages.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/ui tests/test_ui_send.py
git commit -m "feat: preview/approve, phone sending, reports and settings pages"
```

---

### Task 18: End-to-end safety test, README and live run

**Files:**
- Create: `tests/test_end_to_end.py`, `README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the end-to-end tests**

```python
@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
@pytest.mark.parametrize("include_name", [False, True])
def test_full_round_never_crosses_students(conn, tmp_path, fmt, include_name):
    ms0 = get_setting(conn, "message"); ms0["include_name"] = include_name; set_setting(conn, "message", ms0)
    ids = seed_contacts(conn, tmp_path); rid = seed_round(conn, tmp_path, fmt=fmt)
    rr = build_results(conn, rid)
    # owner confirms proposed and picks the top candidate for each review entry
    confirm_links(conn, [(m.stud_id, (m.student_id or m.candidates[0].student_id), m.names[0])
                         for m in rr.links_to_confirm if m.status == "proposed" or m.candidates])
    rr = build_results(conn, rid); ms = message_settings(conn)
    assert get_outbox(conn, rid) == {}                                   # nothing approved by processing
    approve(conn, rid, rr.students, ms)
    adv = {r[0]: r for r in builders.SAMPLE_ROWS}; mains = {r[0]: r for r in builders.MAINS_ROWS}
    assert get_outbox(conn, rid)                                         # something was approved
    for sid, rec in get_outbox(conn, rid).items():
        res = next(s for s in rr.students if s.student_id == sid)
        for title, rows in (("Advance Exam - 4", adv), ("Mains Exam - 4", mains)):
            _, _, _, m, p, c, t = rows[res.stud_id]
            assert (f"*{title} Marks*\n\nMaths - {m}\nPhysics - {p}\nChemistry - {c}"
                    f"\n\n*Total Marks - {t}*") in rec.body
        others = [n for k, n, *_ in builders.SAMPLE_ROWS if k != res.stud_id]
        assert not any(title_name(n) in rec.body for n in others)
        assert (title_name(res.name) in rec.body) == include_name
        assert rec.phone == conn.execute("select phone from students where id=?", (sid,)).fetchone()[0]

def test_every_row_and_contact_accounted_for(conn, tmp_path):
    seed_contacts(conn, tmp_path); rid = seed_round(conn, tmp_path)
    rr = build_results(conn, rid)
    in_files = {r.stud_id for _, r in round_rows(conn, rid)}
    seen = ({s.stud_id for s in rr.students} | {m.stud_id for m in rr.links_to_confirm}
            | {m.stud_id for m in rr.not_found} | {m.stud_id for m in rr.ignored})
    assert in_files <= seen
    contacts = {r["id"] for r in list_students(conn)}
    placed = ({s.student_id for s in rr.students} | {r["id"] for r in rr.not_in_any_file}
              | {c.student_id for m in rr.links_to_confirm for c in m.candidates}
              | {m.student_id for m in rr.links_to_confirm if m.student_id})
    assert contacts <= placed

def test_round_two_links_by_id(conn, tmp_path): ...   # second round: links_to_confirm == [] and all linked
def test_cannot_send_unapproved(conn, tmp_path): ...  # mark_sent on an id with no row → ValueError
```

- `test_round_two_links_by_id`: in a second round, `links_to_confirm == []` and every student is linked.
- `test_cannot_send_unapproved`: `mark_sent` on an id with no row raises `ValueError`.

- [ ] **Step 2: Run them.**

Run: `pytest tests/test_end_to_end.py -v`
Expected: PASS. A failure here means a real bug in an earlier task: fix it there, not in the test.

- [ ] **Step 3: Write `README.md`**

Plain language, for the owner, with sections:
1. **What it does**
2. **Install**
   - Windows and macOS: Python 3.10+ from python.org
   - `python -m venv .venv`, activate, `pip install -r requirements.txt`
3. **Start it**: `streamlit run app.py`, which opens `http://localhost:8501`.
4. **First run**: set the password.
5. **Every two weeks**: Contacts (upload if changed) → New round (upload Advance + Mains) → Needs attention → Preview & approve → Send → Reports.
6. **Settings**: message format, the name line, exam rules, link type.
7. **Where data lives**: `data/`. Back it up by copying the folder. Never share it, and keep disk encryption on (BitLocker / FileVault).
8. **Troubleshooting**:
   - scanned PDFs (stage 2)
   - "changed since approval"
   - "Unknown — check" after an interrupted API send (stage 3)

- [ ] **Step 4: Live run check**

1. Start `streamlit run app.py --server.headless true` with `MARKSAPP_DATA_DIR` pointing at a scratch directory.
2. With Playwright (Chromium): set a password; upload the fixture contacts and the Advance + Mains xlsx; save links; approve all Ready; open the Send page.
3. Screenshot each page (scale 1).

Expected: no Streamlit exception boxes. The Send page shows an "Open in WhatsApp" link whose `href` starts with `https://wa.me/91`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_end_to_end.py README.md
git commit -m "test: end-to-end safety checks; docs: install and usage guide"
```

---

## Stage 2 — OCR fallback for scanned PDFs

### Task 19: OCR reader

**Files:**
- Create: `marksapp/readers/ocr.py`
- Modify: `requirements.txt` (add `PyMuPDF>=1.24`, `pytesseract>=0.3.10`), `marksapp/ui/round_page.py` (`prepare_upload`), `README.md` (Tesseract install: Windows UB-Mannheim installer; macOS `brew install tesseract`)
- Test: `tests/test_ocr.py`

**Interfaces:**
- Consumes: `Grid`, `NoTextInPdf` (Task 6); `prepare_upload` (Task 16); `add_exam(via_ocr=True)` (Task 11).
- Produces:
  - `ocr_available() -> bool`: `pytesseract.get_tesseract_version()` succeeds.
  - `ocr_pdf_to_grid(data: bytes) -> Grid`

**Approach:**
1. Render each page with PyMuPDF at 300 dpi.
2. Run `pytesseract.image_to_data(output_type=DICT, config="--psm 6")`.
3. Group words by `(block, par, line)` into rows. Sort by `left`.
4. Start a new cell wherever the horizontal gap is more than 1.5× the line's median word height.
5. Cell text = the words joined with spaces.

**Upload change:** in `prepare_upload`, when `NoTextInPdf` is raised:
- if `ocr_available()` → use the OCR grid with `via_ocr = True`, and show a warning that every student from this file will need individual review
- otherwise → `error = "This PDF is a scanned image and OCR is not installed. Install Tesseract (see README) or ask for the Excel/PDF export."`

- [ ] **Step 1: Write the failing tests** (skipped when Tesseract is missing)

```python
needs_tess = pytest.mark.skipif(not ocr_available(), reason="Tesseract not installed")

@needs_tess
def test_ocr_reads_most_ids(tmp_path, marks_files):
    scanned = image_only_copy(marks_files["pdf"], tmp_path)   # helper: render pages → image-only PDF
    f = parse_marks_grid(ocr_pdf_to_grid(scanned.read_bytes()))
    ids = {r.stud_id for r in f.rows}
    assert len(ids & {r[0] for r in builders.SAMPLE_ROWS}) >= 6

@needs_tess
def test_ocr_rows_never_bulk_approved(conn, tmp_path, marks_files):
    # add the OCR-parsed exam via add_exam(via_ocr=True), link, build_results:
    # every student has "ocr" issue and approve(..) without allow_review returns []

def test_prepare_upload_without_tesseract(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("marksapp.readers.ocr.ocr_available", lambda: False)
    p = tmp_path / "s.pdf"; builders.write_blank_pdf(p)
    assert "OCR is not installed" in prepare_upload(conn, p.read_bytes(), p.name, None).error
```

`test_ocr_rows_never_bulk_approved`: add the OCR-parsed exam with `add_exam(via_ocr=True)`, link the students and run `build_results`. Every student has an `ocr` issue, and `approve(..)` without `allow_review` returns `[]`.

- [ ] **Step 2: Install Tesseract to run the OCR tests**

Run `apt-get install -y tesseract-ocr`. If that fails, note that the OCR tests were skipped.

Run: `pytest tests/test_ocr.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `ocr.py` and the `prepare_upload` change.**

- [ ] **Step 4: Run tests — expect PASS (or SKIPPED, with the reason reported).**

- [ ] **Step 5: Commit**

```bash
git add marksapp/readers/ocr.py marksapp/ui/round_page.py requirements.txt README.md tests/test_ocr.py
git commit -m "feat: OCR fallback for scanned PDFs (always needs review)"
```

---

## Stage 3 — Official WhatsApp Cloud API

### Task 20: Secrets store, API client and batch sending

**Files:**
- Create: `marksapp/secrets_store.py`, `marksapp/sending/__init__.py`, `marksapp/sending/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `outbox` transitions and `check_current` (Task 13); `build_results` (Task 12); `message_settings` (Task 13); `get_setting` (Task 5).
- Produces (`secrets_store.py`):
  - `secrets_path() -> Path`: `data_dir() / "secrets.json"`.
  - `load_secrets() -> dict`: `{}` if the file is missing.
  - `save_secrets(d: dict) -> None`: `chmod 600` on POSIX.
- Produces (`sending/api.py`):
  - `class ApiError(Exception)`: attributes `code: int | None`, `message: str`, `stop: bool`.
  - `STOP_CODES = {0, 4, 190, 80007, 130429, 131048, 131056}`. HTTP 401 also stops.
  - `class WhatsAppClient(phone_number_id: str, token: str, api_version: str = "v24.0", session: requests.Session | None = None, timeout: float = 30.0)`
    - `.send_template(to_e164: str, template: str, language: str, params: list[str]) -> str`: returns the `wamid`.
  - `round_shape(result: StudentResult) -> str`: `"+".join(e.exam_type for e in result.exams)`, e.g. `"Advance Exam+Mains Exam"`.
  - `template_params(result: StudentResult, include_name: bool) -> list[str]`
    - optional `title_name(name)` first
    - then per exam: `str(exam_number)` (or `display_name` when the number is `None`), maths, physics, chemistry, total (each `.display()`)
  - `validate_param(p: str) -> None`: `ValueError` if empty, or containing `\n`, `\t` or 5+ consecutive spaces.
  - `BatchOutcome(accepted: int, failed: int, unknown: int, skipped_changed: int, stopped_reason: str | None)`
  - `send_batch(conn, round_id: int, student_ids: list[int], client: WhatsAppClient, *, sleep=time.sleep) -> BatchOutcome`

**Request** to `POST https://graph.facebook.com/{api_version}/{phone_number_id}/messages`:
- header `Authorization: Bearer {token}`
- JSON:

```json
{"messaging_product": "whatsapp", "to": "<digits without +>", "type": "template",
 "template": {"name": "<template>", "language": {"code": "<language>"},
              "components": [{"type": "body", "parameters": [{"type": "text", "text": "<p1>"}, "..."]}]}}
```

**`send_batch` rules:**
- Before any call, check the template mapping (`get_setting("api")["templates"][round_shape]`). If any selected student's shape has no template → `ValueError("No template set for: <shape>")`.
- Each eligible row (status `approved` or `failed`):
  1. `check_current`, or count it as `skipped_changed`.
  2. `mark_sending`, which commits.
  3. Call the API.
- Outcomes:
  - success → `mark_accepted`
  - `ApiError` → `mark_failed`; if `stop`, end the batch with `stopped_reason = message`
  - `requests.Timeout` → `mark_unknown` (it may have been delivered, so it is never resent automatically)
  - other `requests.RequestException` → `mark_failed`
- Sleep `pause_seconds` between calls.
- Rows in `unknown`, `sent` or `accepted` are never sent.

- [ ] **Step 1: Write the failing tests**

Use a `FakeSession` whose `.post(url, json, headers, timeout)` replays queued responses or exceptions and records each call.

```python
def test_request_shape(): ...        # url contains "/v24.0/PNID/messages"; json["to"] == "919876543201";
                                     # params texts == ["4","41","32","17","90","4","62","17","16","95"]
def test_success_marks_accepted(conn, tmp_path): ...   # status accepted, api_message_id "wamid.X", attempts 1
def test_undeliverable_continues(conn, tmp_path): ...  # code 131026 → failed; next student still sent
def test_auth_error_stops(conn, tmp_path): ...         # code 190 → stopped_reason set; remaining stay approved
def test_timeout_is_unknown_and_not_resent(conn, tmp_path): ...
def test_missing_template_raises_before_any_call(conn, tmp_path): ...  # FakeSession.calls == []
def test_validate_param():
    with pytest.raises(ValueError): validate_param("a\nb")
    with pytest.raises(ValueError): validate_param("a     b")
def test_secrets_not_in_db(conn, tmp_path):
    save_secrets({"access_token": "SECRET-TOKEN-123"})
    dump = "\n".join(conn.iterdump())
    assert "SECRET-TOKEN-123" not in dump
    if os.name == "posix": assert oct(secrets_path().stat().st_mode)[-3:] == "600"
```

- `test_request_shape`: the URL contains `"/v24.0/PNID/messages"`, `json["to"] == "919876543201"`, and the parameter texts are `["4","41","32","17","90","4","62","17","16","95"]`.
- `test_success_marks_accepted`: status `accepted`, `api_message_id == "wamid.X"`, `attempts == 1`.
- `test_undeliverable_continues`: error code 131026 → `failed`, and the next student is still sent.
- `test_auth_error_stops`: error code 190 → `stopped_reason` is set and the remaining rows stay `approved`.
- `test_timeout_is_unknown_and_not_resent`: a timeout leaves the row `unknown`, and a second batch does not send it.
- `test_missing_template_raises_before_any_call`: `ValueError`, and `FakeSession.calls == []`.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `secrets_store.py` and `sending/api.py`.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add marksapp/secrets_store.py marksapp/sending tests/test_api.py
git commit -m "feat: WhatsApp Cloud API client with safe batch sending"
```

---

### Task 21: API settings, API send mode and the Meta setup guide

**Files:**
- Modify: `marksapp/ui/settings_page.py`, `marksapp/ui/send_page.py`, `README.md`
- Create: `docs/whatsapp-api-setup.md`
- Test: `tests/test_ui_api.py`

**Interfaces:**
- Consumes: Task 20.

**Settings → WhatsApp API section:**
- Inputs:
  - Phone Number ID
  - WhatsApp Business Account ID (optional)
  - Access token: a password input; once saved it shows `"saved, ends …{last4}"` and is never displayed again
  - API version (default `v24.0`), language (default `en`)
  - one template name per round shape: one input for each two-type combination of the exam rules in rule order, plus each single type
  - pause seconds
  - **Use the API for sending** toggle
- Credentials go through `save_secrets`. Everything else goes through `set_setting("api", ...)`.

**Send page when the API is enabled:**
- A mode radio: **From my phone** / **Through WhatsApp API**.
- API mode shows:
  1. the template name and filled parameters for the first student
  2. **Send all approved ({n})** and **Send selected**, which call `send_batch` with a spinner
  3. the outcome counts and `stopped_reason` (`st.error`)
  4. an **Unknown — check** list per row: **It arrived** (`mark_sent` with `method="api"`; allowed from `unknown` — add `unknown → sent` to the Task 13 transitions, with a test) and **Send again** (`reset_for_resend`)
  5. **Retry failed** → `send_batch` over the failed rows

**`docs/whatsapp-api-setup.md`** (plain language for the owner):
1. Create a Meta Business account and complete business verification.
2. Create a WhatsApp Business Account and add a phone number. It cannot stay active in the normal WhatsApp app unless Meta's coexistence option is used.
3. Set the display name and add a payment method.
4. Submit these Utility templates (language English). Variables are never first or last:

   `marks_adv_mains`:
   ```
   *Advance Exam - {{1}} Marks*

   Maths - {{2}}
   Physics - {{3}}
   Chemistry - {{4}}

   *Total Marks - {{5}}*

   *Mains Exam - {{6}} Marks*

   Maths - {{7}}
   Physics - {{8}}
   Chemistry - {{9}}

   *Total Marks - {{10}}*

   — <your name / institute>
   ```

   Plus `marks_adv` and `marks_mains` (one block each), and the variants with the name line for when the name setting is on (`Student: *{{1}}*` first, with the other numbers shifted).
5. Create a System User with a permanent token (`whatsapp_business_messaging` permission). Copy the Phone Number ID.
6. Collect parents' consent (e.g. on the admission form or a WhatsApp reply). Meta requires opt-in.
7. Test with Meta's free test number (up to 5 verified recipients) before going live.
8. Check the current Graph API version in Meta's docs and update it in Settings.
9. Fees: Meta charges per Utility message. See Meta's pricing page for India.

- [ ] **Step 1: Write the failing tests**

```python
def test_token_never_rendered_back(app_env, conn): ...      # save token via settings form; page text lacks it, shows last4
def test_api_mode_hidden_when_disabled(app_env, conn): ...  # no "Through WhatsApp API" radio option
def test_unknown_it_arrived(conn, tmp_path): ...            # unknown → mark_sent(method="api") allowed
```

- `test_token_never_rendered_back`: save a token through the Settings form. The page text does not contain it and shows the last 4 characters.
- `test_api_mode_hidden_when_disabled`: with the API off, there is no "Through WhatsApp API" option.
- `test_unknown_it_arrived`: `unknown` → `mark_sent(method="api")` is allowed.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement the UI changes, the transition, and write the guide.**

Link the guide from the README.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all pass (OCR tests may be skipped, with the reason shown).

- [ ] **Step 5: Commit**

```bash
git add marksapp/ui marksapp/outbox.py docs/whatsapp-api-setup.md README.md tests/test_ui_api.py tests/test_outbox.py
git commit -m "feat: API settings and sending mode; Meta setup guide"
```

---

## Later (not in this plan)

- Cumulative performance reports (spec §2 non-goal for this version). The data is already kept in `marks` per student.
- Delivered/read ticks (they need a hosted webhook).
