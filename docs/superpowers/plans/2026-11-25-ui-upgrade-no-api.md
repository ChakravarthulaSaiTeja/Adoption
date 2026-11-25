# UI Upgrade, Automatic API/Normal Sending, and Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Streamlit app a clean, consistent look and a Home page, plus a fast
WhatsApp-desktop sending flow. The app picks the API automatically when a key is
saved, and otherwise the normal method. Fix every bug found in the build check.

**Architecture:**
- **Engine changes stay small and test-first:** phones, outbox, sending/api, and a
  new `sending/method.py`.
- **UI changes go through a new `marksapp/ui/style.py`** (CSS, bubble, status
  labels, header), used by every page. There is a new `ui/home_page.py`.
- **Pages keep calling the same domain functions.** The safety checks (approval,
  hash at send, shared-number confirmation) are untouched.

**Tech Stack:** Python ≥ 3.10, Streamlit ≥ 1.40, pytest + `streamlit.testing.v1.AppTest`, Playwright (live check only).

**Spec:** `docs/superpowers/specs/2026-11-25-ui-upgrade-no-api-design.md` (builds on `2026-11-19-student-marks-whatsapp-design.md`)

## Global Constraints

**Platform and data**
- Must run on Python 3.10+ and on macOS and Windows. All 175 existing tests keep
  passing.
- No real student data in the repo.

**Colour and links**
- Accent colour `#128C7E`. No WhatsApp logos or brand names beyond the word
  "WhatsApp".
- "Open in WhatsApp" is a raw HTML link built only from `outbox.phone_link`:
  - desktop → `target="_self"`
  - web → `target="marks_whatsapp"`
  - wa.me → `target="_blank"`
- Never use `st.link_button` for WhatsApp.
- The `link_kind` default becomes `"desktop"`.

**Choosing how to send**
- `"api"` when the secrets hold both `phone_number_id` and `access_token`;
  otherwise `"phone"`.
- The old `api["enabled"]` flag is ignored.

**Safety**
- No change weakens: approval-only sending, the `content_hash` check at send time,
  the shared-number confirmation, the round lock, or "fuzzy never links".

## Review Focus

1. **Names with special characters in links:** a name or message with `&`, `#`, `?`,
   Telugu script or emoji must survive the link intact (fully URL-encoded) → Task 5
   `test_link_html_encodes_everything`.
2. **API key saved but no template for this round:** the Send page explains, and
   offers the normal method instead of failing → Task 5
   `test_api_without_template_offers_normal_method`.
3. **Numbers typed `00971…`:** the international `00` prefix means the same as
   `+` → Task 1 `test_double_zero_prefix_is_international`.
4. **Changing the message format after approving:** every approval is dropped on
   Preview, with a notice → Task 7 `test_preview_drops_approvals_after_format_change`.
5. **Switching between API and normal mid-round:** a message sent one way can never
   be sent again the other way without "Send again" → Task 3
   `test_phone_sent_message_is_not_sent_by_api`.

---

## File Structure

```
marksapp/phones.py                 + international numbers
marksapp/outbox.py                 atomic status moves; drop_stale_approvals (moved from send_page)
marksapp/contacts.py               audit old/new stud_id
marksapp/sending/api.py            ConnectionError→unknown; refuse exam without number
marksapp/sending/method.py   NEW   sending_method, remove_api_key
marksapp/settings.py               link_kind default "desktop"
marksapp/ui/style.py         NEW   inject_css, bubble, status_label, header, whatsapp_link_html
marksapp/ui/home_page.py     NEW   round_steps (pure) + render
marksapp/ui/send_page.py           new card flow, automatic method, fallback switch
marksapp/ui/preview_page.py        stale drop, labels, per-round selection, bubble
marksapp/ui/attention_page.py      every issue listed, duplicate-row help
marksapp/ui/settings_page.py       bubble preview, order, API section with method + remove key
marksapp/ui/round_page.py          OCR total warning + cache, column override, no duplicate columns
marksapp/ui/contacts_page.py       remember contact columns
marksapp/ui/common.py              sidebar round summary
app.py, .streamlit/config.toml     Home page, navigation order, theme
README.md                          updated
```

---

### Task 1: International parent numbers

**Files:**
- Modify: `marksapp/phones.py`
- Test: `tests/test_phones.py`

**Interfaces:**
- Produces: `normalise_phone(raw) -> PhoneResult` also accepts international
  numbers; `pretty_phone(e164) -> str` handles them.

**Rules:**
- After the existing number clean-up, text starting with `+` or `00` is
  international:
  - Starting `91` (after the `+`/`00`) → the Indian rules exactly as now.
  - Otherwise the digits must be 8–15 long and must not start with 0 → `+<digits>`.
    Else: "Not a valid international number".
- Text without `+`/`00` keeps the current Indian rules, except that a leading `0`
  followed by 10 digits is still Indian.
- "More than one number" still wins over all of these.

- [ ] **Step 1: Write the failing tests**

```python
def test_international_with_plus():
    r = normalise_phone("+971 50 123 4567")
    assert r.ok and r.e164 == "+971501234567"
    assert pretty_phone("+971501234567") == "+971501234567"

def test_double_zero_prefix_is_international():
    assert normalise_phone("00971501234567").e164 == "+971501234567"
    assert normalise_phone("0091 98765 43210").e164 == "+919876543210"

def test_bad_international():
    assert normalise_phone("+1 23").problem == "Not a valid international number"

def test_indian_rules_unchanged():
    assert normalise_phone("+91 5876543210").problem == "Must start with 6, 7, 8 or 9"
    assert normalise_phone("09876543210").e164 == "+919876543210"
```

Also update `test_rejected_forms`: `"+1 415 555 0100"` is now valid (`+14155550100`).

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_phones.py -q` — expected: FAIL.
- [ ] **Step 3: Implement** the rules in `normalise_phone`, and make `pretty_phone`
  return non-Indian numbers unchanged.
- [ ] **Step 4: Run the full suite.** Expected: PASS. Update any test that relied on
  foreign numbers being rejected, and note the change.
- [ ] **Step 5: Commit** `feat: accept parents' international numbers (+ or 00 prefix)`

---

### Task 2: Outbox integrity and the stale-approval helper

**Files:**
- Modify: `marksapp/outbox.py`, `marksapp/contacts.py`, `marksapp/ui/send_page.py`
- Test: `tests/test_outbox.py`, `tests/test_contacts.py`

**Interfaces:**
- Produces: `outbox.drop_stale_approvals(conn, round_id) -> int`. This is the
  current `send_page.drop_stale`, moved. `send_page.drop_stale` stays as an alias
  so existing tests pass.
- `_move` becomes atomic:

  ```sql
  UPDATE messages SET … WHERE id = ? AND status IN (<allowed-from>)
  ```

  - `rowcount == 0` → re-read the row and raise the same `ValueError`
    ("Message not found — approve it first" or "Cannot go from X to Y").
- `update_student` audit `student_updated` adds `old_stud_id` and `new_stud_id`.

- [ ] **Step 1: Failing tests**

```python
def test_move_is_atomic_against_a_stale_reader(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    [sid] = approve(conn, rid, _ready(rr)[:1], message_settings(conn))
    mid = get_outbox(conn, rid)[sid].id
    other = connect()  # a second session
    mark_sent(other, mid)
    with pytest.raises(ValueError):
        mark_sent(conn, mid)
    assert conn.execute("select attempts from messages where id=?", (mid,)).fetchone()[0] == 1

def test_drop_stale_approvals_counts(conn, tmp_path): ...   # approve 2, change one phone → returns 1

def test_unlink_audit_records_ids(conn, tmp_path):
    ids = seed_contacts(conn, tmp_path)
    update_student(conn, ids["Syed Afreen"], stud_id="5")
    update_student(conn, ids["Syed Afreen"], stud_id=None)
    d = json.loads(audit.recent(conn)[0]["details"])
    assert (d["old_stud_id"], d["new_stud_id"]) == ("5", None)
```

`test_drop_stale_approvals_counts`: approve two students, change one student's
phone; the function returns 1.

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `fix: atomic message status moves; audit ID changes; shared stale-approval helper`

---

### Task 3: Choosing how to send, and API fixes

**Files:**
- Create: `marksapp/sending/method.py`
- Modify: `marksapp/sending/api.py`
- Test: `tests/test_method.py`, `tests/test_api.py`, `tests/test_end_to_end.py`

**Interfaces:**
- Produces:
  - `sending_method(conn) -> Literal["api", "phone"]`
  - `remove_api_key() -> None`: deletes `access_token` from the secrets and keeps
    the other fields.
  - `api.template_params` raises `ValueError("<display name> has no exam number,
    which the API template needs")` for an exam whose `exam_number is None`.
  - In `send_batch`, that `ValueError` marks the message failed with this text,
    before any request is made.
  - `requests.ConnectionError` → `mark_unknown` (it may have gone out). Other
    `RequestException`s → failed.

- [ ] **Step 1: Failing tests**

```python
# tests/test_method.py
def test_phone_without_key(conn): assert sending_method(conn) == "phone"
def test_api_with_key(conn):
    save_secrets({"phone_number_id": "1", "access_token": "T"}); assert sending_method(conn) == "api"
def test_enabled_flag_ignored(conn):
    api = get_setting(conn, "api"); api["enabled"] = True; set_setting(conn, "api", api)
    assert sending_method(conn) == "phone"
def test_remove_key(conn):
    save_secrets({"phone_number_id": "1", "access_token": "T"}); remove_api_key()
    assert sending_method(conn) == "phone" and load_secrets() == {"phone_number_id": "1"}

# tests/test_api.py
def test_connection_error_is_unknown(conn, tmp_path): ...       # FakeSession raising requests.ConnectionError → unknown
def test_skips_message_changed_since_approval(conn, tmp_path): ... # update phone after approve → skipped_changed == 1, no call
def test_exam_without_number_refused(): ...                       # template_params on an exam_number=None result raises
def test_phone_sent_message_is_not_sent_by_api(conn, tmp_path):
    rid, ids = _setup(conn, tmp_path, n=1)
    mark_sent(conn, get_outbox(conn, rid)[ids[0]].id)          # sent from the owner's phone
    fake = FakeSession()
    send_batch(conn, rid, ids, WhatsAppClient("P", "T", session=fake), sleep=lambda s: None)
    assert fake.calls == []

# tests/test_end_to_end.py
def test_mixed_excel_and_pdf_round(conn, tmp_path): ...  # Advance xlsx + Mains pdf → bodies match both fixtures
```

- `test_connection_error_is_unknown`: a FakeSession raising
  `requests.ConnectionError` leaves the message `unknown`.
- `test_skips_message_changed_since_approval`: change the phone after approval;
  `skipped_changed == 1` and no request is made.
- `test_exam_without_number_refused`: `template_params` on a result whose
  `exam_number` is `None` raises.
- `test_mixed_excel_and_pdf_round`: an Advance `.xlsx` and a Mains `.pdf` in one
  round; every message body matches both fixtures.

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: choose API or normal sending automatically; API error handling fixes`

---

### Task 4: Style module and theme

**Files:**
- Create: `marksapp/ui/style.py`
- Modify: `.streamlit/config.toml`, `marksapp/settings.py`
- Test: `tests/test_style.py`

**Interfaces:**
- Produces:
  - `inject_css() -> None`
  - `header(title: str, subtitle: str = "") -> None`
  - `bubble(body: str) -> str`: HTML.
    - escapes `<`, `>` and `&`
    - turns `*text*` (on one line) into `<b>text</b>`
    - turns newlines into `<br>`
    - wraps the result in `<div class="wa-bubble">`
  - `status_label(status: str) -> str`. Mapping:
    - `ready` → `🟢 Ready`
    - `review` → `🟡 Needs review`
    - `blocked` → `🔴 Blocked`
    - `approved` → `✅ Approved`
    - `sent` and `accepted` → `📤 Sent`
    - `failed` → `⚠️ Failed`
    - `unknown` → `⚠️ Unknown — check`
    - `skipped` → `⏭ Skipped`
    - `sending` → `⏳ Sending`
  - `whatsapp_link_html(url: str, kind: str, label: str = "Open in WhatsApp") -> str`:
    an `<a class="wa-btn" href=… target=…>`, with the target per Global Constraints
    and the href HTML-escaped.
- Theme in `config.toml`:

  ```toml
  [theme]
  primaryColor = "#128C7E"
  backgroundColor = "#FFFFFF"
  secondaryBackgroundColor = "#F3F5F4"
  textColor = "#1C2421"
  font = "sans serif"
  ```

- `DEFAULTS["link_kind"] = "desktop"`.

- [ ] **Step 1: Failing tests**

```python
def test_bubble_bold_and_escape():
    html = bubble("*Advance Exam - 4 Marks*\n\nMaths - 41 <b>x</b> & y")
    assert "<b>Advance Exam - 4 Marks</b>" in html and "<br>" in html
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in html and html.startswith('<div class="wa-bubble">')

def test_status_labels():
    assert status_label("ready") == "🟢 Ready" and status_label("accepted") == "📤 Sent"

def test_link_targets():
    assert 'target="_self"' in whatsapp_link_html("whatsapp://send?phone=91&text=a%26b", "desktop")
    assert 'target="marks_whatsapp"' in whatsapp_link_html("https://web.whatsapp.com/send?x", "web")
    assert 'href="whatsapp://send?phone=91&amp;text=a%26b"' in whatsapp_link_html("whatsapp://send?phone=91&text=a%26b", "desktop")

def test_default_link_kind_is_desktop(conn):
    assert get_setting(conn, "link_kind") == "desktop"
```

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: style module, theme and desktop-app default`

---

### Task 5: Send page — new card flow and automatic method

**Files:**
- Modify: `marksapp/ui/send_page.py`, `marksapp/ui/settings_page.py`
- Test: `tests/test_ui_send.py`, `tests/test_ui_api.py`, `tests/test_outbox.py`

**Interfaces:**
- Consumes: `sending_method`, `remove_api_key` (Task 3); `drop_stale_approvals`
  (Task 2); `style.*` (Task 4).

**Send page:**
1. `header("Send", <one line>)`, then a line: "Sending through: your WhatsApp
   (desktop app / WhatsApp Web / WhatsApp link)" or "Sending through: WhatsApp
   Business API".
2. **If `sending_method == "api"`:**
   - API mode, plus a toggle "Send from my own WhatsApp instead" (key
     `use_phone_instead`) that switches this visit to the normal flow.
   - If the round has no template for its exam shape: an info box naming the shape
     and pointing to Settings, and the normal flow is shown under it.
3. **Normal flow card:**
   - `st.progress(sent / total)` and "n of m sent"
   - the student name as a heading, and the parent's number
   - `st.markdown(bubble(body))`
   - `st.markdown(whatsapp_link_html(phone_link(...), kind))`
   - buttons: **✅ Sent — next** (key `mark_sent_{id}`), **Couldn't send** with a
     reason, **Skip**
   - caption: "Already sent this one? Click ✅ Sent — next."
   - All three button actions keep the existing callbacks bound to the message id.

**Settings page API section** (visible, not collapsed):
- shows the current method
- the existing fields
- **Remove API key** (key `api_remove`)
- The "Use the API for sending" tick box is removed.

- [ ] **Step 1: Failing tests**

```python
def test_link_html_encodes_everything():
    url = phone_link("+919876543201", "*Rāma & Sītā* # ? తెలుగు 🎉", "desktop")
    assert "&" not in url.split("text=")[1] and "#" not in url and "?" not in url.split("?", 1)[1]
    assert decode(url.split("text=")[1]) == "*Rāma & Sītā* # ? తెలుగు 🎉"   # urllib.parse.unquote

def test_send_page_phone_mode_without_key(app_env, conn, tmp_path): ...   # no radio "send_mode", shows a wa-btn link with target _self
def test_send_page_api_mode_with_key(app_env, conn, tmp_path): ...        # save_secrets(pnid+token), template set → "api_send_all" button present
def test_api_without_template_offers_normal_method(app_env, conn, tmp_path): ...  # key saved, no template → info + mark_sent_ button present
def test_use_phone_instead_toggle(app_env, conn, tmp_path): ...           # key+template saved; toggle on → mark_sent_ button present
def test_settings_remove_api_key(app_env, conn): ...                      # save key, click api_remove → sending_method == "phone"
```

- `test_send_page_phone_mode_without_key`: no `send_mode` radio, and a `wa-btn`
  link with `target="_self"` is shown.
- `test_send_page_api_mode_with_key`: with a Phone Number ID, token and template
  saved, the `api_send_all` button is present.
- `test_api_without_template_offers_normal_method`: with a key saved but no
  template, an info box is shown and a `mark_sent_` button is present.
- `test_use_phone_instead_toggle`: with a key and template saved, turning the
  toggle on shows a `mark_sent_` button.
- `test_settings_remove_api_key`: save a key, click `api_remove`;
  `sending_method` is now `"phone"`.

Update the Task-21 tests that used `api.enabled` and the `send_mode` radio.

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: new send flow with desktop-app links; API used automatically when a key is saved`

---

### Task 6: Home page and navigation

**Files:**
- Create: `marksapp/ui/home_page.py`
- Modify: `app.py`, `marksapp/ui/common.py`
- Test: `tests/test_home.py`

**Interfaces:**
- Produces:
  - `Step(number: int, title: str, summary: str, done: bool, page: str)`: a
    dataclass. `page` is a key into the pages dict.
  - `round_steps(conn) -> tuple[sqlite3.Row | None, list[Step]]`: pure. Uses the
    latest round.
  - `render(conn, pages: dict[str, st.Page] | None = None) -> None`. With `pages`
    `None` (as in tests), it shows text and no page links.
- **Step summaries and "done" rules:**
  1. **Contacts** — summary "N students · K numbers to check", where
     K = invalid-or-missing phones + unconfirmed shared groups. Done when N > 0 and
     K == 0.
  2. **Files** — summary lists the exam display names, or "No files yet". Done
     when there is at least one exam.
  3. **Confirm** — summary "N students to confirm" (`links_to_confirm`). Done when
     there are none and the round has exams.
  4. **Approve** — summary "R ready · A approved · B need a look". Done when
     R == 0 and B == 0 and A + sent > 0.
  5. **Send** — summary "S of T sent". Done when T > 0 and S == T.
- **`app.py` pages, in order:** Home (default), Contacts, New round,
  Needs attention, Preview & approve, Send, Reports & history, Settings.
- `common.sidebar_summary(conn)` writes the latest round's "S of T sent" under
  the navigation.

- [ ] **Step 1: Failing tests**

```python
def test_steps_empty(conn):
    rnd, steps = round_steps(conn)
    assert rnd is None and [s.done for s in steps] == [False] * 5

def test_steps_after_linking(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    rnd, steps = round_steps(conn)
    assert steps[1].done and steps[1].summary == "Advance Exam - 4, Mains Exam - 4"
    assert steps[2].summary == "2 students to confirm" and not steps[2].done
    assert "1 number to check" in steps[0].summary or "numbers to check" in steps[0].summary

def test_home_renders(app_env, conn, tmp_path): ...   # AppTest from_function render(get_conn()) → no exception
```

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: Home page with the round's five steps; navigation order`

---

### Task 7: Preview & approve upgrade

**Files:**
- Modify: `marksapp/ui/preview_page.py`
- Test: `tests/test_ui_send.py`

**Changes:**
- Call `drop_stale_approvals` first. If it returns `n > 0`, show
  `st.warning(f"{n} approvals were cleared because marks, numbers or the message format changed. Approve them again.")`.
- The Status column uses `status_label`.
- The table key is `f"prev_table_{round_id}"`. Selected rows map to student ids
  through the row order of the dataframe being displayed, with bounds checks.
- The detail view shows `bubble`, with problems as coloured notes.

- [ ] **Step 1: Failing tests**

```python
def test_preview_drops_approvals_after_format_change(app_env, conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    approve(conn, rid, rr.students, message_settings(conn))
    m = get_setting(conn, "message"); m["include_name"] = True; set_setting(conn, "message", m)
    at = _at("preview_page").run(timeout=30)
    assert any("approvals were cleared" in w.value for w in at.warning)
    assert get_outbox(conn, rid) == {}

def test_preview_shows_status_labels(app_env, conn, tmp_path): ...   # dataframe Status column contains "🟢 Ready"
```

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: preview drops stale approvals, status labels, bubbles`

---

### Task 8: Needs attention completeness, and the Settings layout

**Files:**
- Modify: `marksapp/ui/attention_page.py`, `marksapp/ui/settings_page.py`
- Test: `tests/test_ui_round.py`, `tests/test_ui_send.py`

**Changes:**
- **Needs attention:** a new section "Everything else to check", listing every
  linked student with any issue not already covered above (`absent`, `ocr`,
  `match` reasons other than "differs"):
  - the issue text
  - a fix hint
- **The "appears more than once in the same file" hint:** "Correct the file, then
  on New round upload it again and tick 'Replace the earlier import'."
- **Settings order:** Message format (with a `bubble` preview), How WhatsApp opens
  (desktop first, with a help line about "Always allow"), Exam names, Password,
  WhatsApp Business API.

- [ ] **Step 1: Failing tests**

```python
def test_attention_lists_absent_and_duplicate_rows(app_env, conn, tmp_path):
    ids = seed_contacts(conn, tmp_path); rid = seed_round(conn, tmp_path); confirm_proposed(conn, rid)
    update_student(conn, ids["Syed Afreen"], stud_id="999")      # linked but absent from both files
    at = AppTest.from_function(attention_script).run(timeout=30)
    text = "\n".join(str(x.value) for x in at.markdown) + "\n".join(str(x.value) for x in at.warning)
    assert "Absent from Advance Exam - 4" in text

def test_settings_preview_is_a_bubble(app_env, conn): ...   # markdown contains 'class="wa-bubble"'
```

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: needs-attention lists every issue; settings reordered with bubble preview`

---

### Task 9: New round and Contacts — OCR warning and cache, column control

**Files:**
- Modify: `marksapp/ui/round_page.py`, `marksapp/ui/contacts_page.py`, `marksapp/rounds.py`
- Test: `tests/test_ui_round.py`, `tests/test_rounds.py`

**Interfaces:**
- Produces:
  - `round_page.column_map_problems(cmap: dict[str, int | None]) -> list[str]`.
    It reports:
    - each missing required field: `"Choose a column for <label>"`
    - each column used by more than one field: `"<label A> and <label B> use the same column"`
  - `rounds.save_contact_columns(conn, signature: str, cols: list[int | None]) -> None`
  - `rounds.get_contact_columns(conn, signature: str) -> list[int | None] | None`
    (stored in `layouts` under the key `"contacts:" + signature`)
  - `round_page._ocr_grid(data: bytes)`: wrapped in `st.cache_data`, keyed by the
    file bytes.
- **Upload preview:**
  - OCR file with no total column → warning: "The total column wasn't found in this
    scanned file, so totals can't be cross-checked. Check every total by hand."
  - a "Change columns" expander that reuses the manual mapping UI, even when
    detection worked
  - the Add button is disabled while `column_map_problems` is non-empty

- [ ] **Step 1: Failing tests**

```python
def test_column_map_problems():
    assert column_map_problems({"stud_id": 0, "name": 1, "maths": 2, "physics": 2, "chemistry": 4}) == \
        ["Maths and Physics use the same column"]
    assert "Choose a column for Chemistry" in column_map_problems({"stud_id": 0, "name": 1, "maths": 2, "physics": 3})

def test_contact_columns_remembered(conn):
    assert get_contact_columns(conn, "sig") is None
    save_contact_columns(conn, "sig", [0, 3, None]); assert get_contact_columns(conn, "sig") == [0, 3, None]
```

- [ ] **Step 2: Run** — expected: FAIL.
- [ ] **Step 3: Implement.** The Contacts page uses the saved columns when a file's
  header signature matches (`header_signature` from `readers.marks_layout`), and
  saves them on Apply.
- [ ] **Step 4: Run the full suite** — expected: PASS.
- [ ] **Step 5: Commit** `feat: OCR total warning and cache; change columns; remember contact columns`

---

### Task 10: README, live run and screenshots

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README.**
  - **Home page.**
  - **"How WhatsApp opens":** desktop app recommended on Mac. The first time,
    tick "Always allow".
  - **Choosing how to send:** API if a key is saved, otherwise your WhatsApp, plus
    "Send from my own WhatsApp instead".
  - **International numbers:** write them with `+` or `00`.
- [ ] **Step 2: Live run.** Start Streamlit on a scratch data folder and drive a
  full round with Playwright (password, contacts, confirm shared number, two
  files, save links, approve all, Send: link has `whatsapp://` and `_self`,
  click ✅ Sent — next). Screenshot each page at scale 1 and check them by eye.
  Expected: no exception boxes.
- [ ] **Step 3: Run the full suite on Python 3.10** (a fresh venv from
  `requirements-dev.txt`). Expected: all pass.
- [ ] **Step 4: Commit** `docs: README for the new flow`
