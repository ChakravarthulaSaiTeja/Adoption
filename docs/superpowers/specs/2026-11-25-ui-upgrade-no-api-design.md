# UI Upgrade, Sending Without the API, and Bug Fixes — Design

Date: 2026-11-25
Status: **For approval**
Builds on: `2026-11-19-student-marks-whatsapp-design.md` (all of its safety rules still apply)

## 1. Intent

The owner uses the app every two weeks on a **Mac**, and today uses **WhatsApp Web**
(willing to switch to the **WhatsApp desktop app**).

They want three things:

1. **A nicer, easier app.**
2. **Sending without the WhatsApp Business API as the real way of working.** It
   should be smooth, not feel like a fallback.
3. **Every bug found, fixed.**

The upgrade polishes the existing Streamlit app (approach A). The engine that keeps
each child's marks going to the right parent is not loosened in any way.

## 2. Goals, non-goals, anti-goals

**Goals**

- A consistent, calmer look:
  - a colour theme
  - page headers with a one-line explanation
  - coloured statuses
  - messages shown as WhatsApp-style bubbles with real bold text
- A **Home** page showing where the current round stands and what to do next.
- A **faster Send screen** for sending without the API:
  - progress
  - one student per card
  - "Open in WhatsApp" opens the desktop app, with no browser tabs
  - "✅ Sent — next" moves on in one click
- The API moved out of sight: Settings → a collapsed "Advanced" section. The Send
  page only offers it when it's switched on (already true).
- The bugs below fixed (section 5).

**Non-goals**

- A custom web front end (approach B).
- Detecting automatically that WhatsApp actually sent a message. That's impossible
  without the API: the owner confirms each send.
- Unofficial WhatsApp automation.
- Opening the app from the phone over Wi-Fi.

**Anti-goals: a failure even if it looks better**

- Any change that weakens the existing safety checks:
  - approval
  - the same-number-and-text check at send time
  - shared-number confirmation
  - no fuzzy links
- Anything that sends without the owner's click.
- A new browser tab per student.

## 3. Constraints

- Streamlit, Python ≥ 3.10. Primary platform is macOS with the WhatsApp desktop
  app. It must still work on Windows and with WhatsApp Web.
- All existing tests keep passing. No real student data in the repo.
- Verified in a spike:
  - Streamlit keeps the `target` of raw HTML links.
  - A `whatsapp://send?...` link with `target="_self"` hands over to the desktop
    app without leaving the page.
  - A web link with a named target reuses one tab.
  - Streamlit's built-in `st.link_button` always opens a new tab (`_blank`).

## 4. Approaches

| | Approach | Trade-off |
|---|---|---|
| **A** | **Polish the existing Streamlit app** *(chosen by the owner)* | Same engine and safety checks; much nicer and faster. Still looks like a tidy tool, not a consumer app. |
| B | Rebuild the screens as a custom web app over the same engine | Slickest look; about as much work again as everything so far, and drops Streamlit. |

## 5. Bugs to fix

**Found in this check:**

1. **The WhatsApp link opens a new browser tab for every student**, and the
   `wa.me` link stops at WhatsApp's "Continue to chat" page. Fixed by the new
   link handling in 6.4.
2. **A parent with a foreign number can't be entered at all.** Numbers written with
   `+` and a country code are now accepted (8–15 digits, E.164). Numbers without a
   `+` keep the Indian rules exactly as now.
3. **Preview can show "Approved" for a message whose marks or number changed since.**
   Preview drops stale approvals before showing the table (the same check as the
   Send page) and says how many need approving again.

**Carried over from the last review:**

4. **Needs attention doesn't list every flag.** It now lists everything per student,
   including "Absent? confirm" and "Read from a scanned PDF", with what to do about
   each. A student whose ID appears twice in one file gets an explanation: fix the
   file and use **Replace the earlier import**.
5. **Preview's row selection could carry over to another round.** The selection is
   now kept per round and mapped by student, not by row position.
6. **Scanned PDFs:**
   - a warning when the total column wasn't found, because the total check is then
     off
   - OCR runs once per file, not again on every click
7. **Column choice:**
   - you can override the columns the app found, through a "Change columns" option
   - the contact list's column choice is remembered by its headers
   - two fields can't use the same column
8. **API path (kept, but hidden):**
   - a connection error after the request went out becomes "Unknown — check", not
     "Failed", so it's never retried automatically
   - an exam without a number is refused for API sending, with a clear message
9. **Integrity:**
   - two sessions can't move the same message at once: status changes become a
     single "update where status is still X" step that checks it worked
   - the unlink/relink audit entry records the old and new ID
10. **Missing tests:**
    - the API path skipping messages that changed since approval
    - one round mixing an Excel Advance file and a PDF Mains file

**Not fixed, on purpose:**
- **Forgetting ✅ Sent after sending.** The app can't see a click on a WhatsApp
  link. Instead, the card says "Already sent this one? Click ✅ Sent — next", and
  WhatsApp itself shows the earlier message in the chat when it opens, so a second
  send is easy to spot.
- **Opening the app while an API batch runs elsewhere.** This only affects the
  hidden API and a single owner.

## 6. Design

### 6.1 Look

- **`.streamlit/config.toml` theme:**
  - `primaryColor = "#128C7E"` (a WhatsApp-like green, used only as an accent;
    no WhatsApp logos or branding)
  - light grey secondary background
  - sans-serif font
- **New `marksapp/ui/style.py`:**
  - `inject_css()`: once per page. Bubble style, status chips, card spacing, wider
    content.
  - `bubble(body) -> str`: escapes HTML, renders `*bold*` as bold and newlines as
    line breaks, and returns a green WhatsApp-like bubble. Used in Preview, Send and
    the Settings preview.
  - `status_label(text) -> str`: dots for tables (Streamlit tables can't show
    HTML):
    - 🟢 Ready
    - 🟡 Needs review
    - 🔴 Blocked
    - ✅ Approved
    - 📤 Sent
    - ⚠️ Failed / Unknown
    - ⏭ Skipped
  - `header(title, subtitle)`: a consistent page heading.

### 6.2 Home page (new, the landing page after login)

"This round" shows the latest round as five steps. Each step has a count, a
done/to-do mark, and a button that opens its page:

```
Round of 25-Nov-2026
 ✔ 1 Contacts        42 students · 1 number to check     [Open]
 ✔ 2 Files           Advance Exam - 4, Mains Exam - 4    [Open]
 • 3 Confirm         2 students to confirm               [Open]
   4 Approve         38 ready · 0 approved               [Open]
   5 Send            0 of 0 sent                         [Open]
```

With no round yet, it shows a "Start a round" button and a three-line how-to.

The counts come from the existing functions: `list_students`,
`unconfirmed_shared_numbers`, `list_exams`, `build_results`, `get_outbox`. Pages
are linked with `st.page_link`, using the page objects from `app.py`.

### 6.3 Preview & approve

- The status column uses the labels from 6.1. The exam columns show totals.
- Stale approvals are dropped first (bug 3), with a notice.
- The detail view shows the message as a bubble, with its problems as coloured
  notes.
- The bulk-approval buttons work as before.

### 6.4 Send (without the API)

- **Settings → "How WhatsApp opens":**
  - **WhatsApp desktop app**: the default, recommended on Mac and Windows.
  - **WhatsApp Web**: reuses one tab named `marks_whatsapp`.
  - **WhatsApp link (`wa.me`)**: for phones.
  - The default changes from `wa.me` to desktop.
- **The "Open in WhatsApp" button is a styled HTML link** (`st.markdown` with
  `unsafe_allow_html`), not `st.link_button`:
  - desktop: `whatsapp://send?phone=…&text=…` with `target="_self"`
  - web: `https://web.whatsapp.com/send?...` with `target="marks_whatsapp"`
  - wa.me: `_blank`
  - The URL is built only by `outbox.phone_link`, which is already tested.
- **The card shows:**
  - "n of m sent" with a progress bar
  - student, number, message bubble
  - **Open in WhatsApp**
  - **✅ Sent — next** (the existing callback bound to the message id)
  - **Couldn't send** with a reason
  - **Skip**
  - the hint "Already sent this one? Click ✅ Sent — next"
- The filters (All / Selected / Failed only) and the "Already sent" list with
  **Send again** stay.
- **First-time tip:** the first time a link opens the desktop app, the Mac browser
  asks "Open WhatsApp?". Tick "Always allow". The README gets this line.

### 6.5 Settings

The order:

1. Message format, with the bubble preview
2. How WhatsApp opens
3. Exam names
4. Password
5. **Advanced: WhatsApp Business API (optional)**, collapsed, with everything that
   exists today

### 6.6 Navigation

- Pages, in order: **Home**, Contacts, New round, Needs attention,
  Preview & approve, Send, Reports & history, Settings.
- The sidebar shows the app name, and a one-line round summary under the page
  list.

## 7. Build order

Each step is tested before the next.

1. **Bug fixes in the engine** (bugs 2, 8, 9, 10 and 3's helper), each test-first.
2. **Style module and theme**, then the Preview and Settings bubbles.
3. **Send screen and link handling** (bug 1), then the Home page and navigation.
4. **Needs attention completeness**, Preview selection, OCR warning and caching,
   column override and memory (bugs 4–7).
5. **README updates**, then a live run of a full round in a browser, with
   screenshots for the owner.

## 8. Left to the builder

- Exact CSS, spacing and wording of the one-line explanations.
- How the Home page lays out its step cards.
- How OCR results are cached (`st.cache_data` keyed by file hash).

## 9. Calls made without the owner (check these)

- **Accent colour:** WhatsApp-like green, `#128C7E`.
- **The desktop app becomes the default** for "How WhatsApp opens".
- **Home becomes the first page** after login.
- **The API stays in the app,** hidden under Advanced, rather than being removed.
- **Foreign numbers are accepted** only when written with `+` and a country code.
- **"Forgot to click ✅ Sent"** is handled with a hint, not a new status. The app
  can't see clicks on WhatsApp links.
