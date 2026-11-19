# Student Marks to Parents on WhatsApp — Design

Date: 2026-11-19
Status: **For approval**

---

## 1. Intent

Every two weeks the owner of this app (a JEE coaching teacher/coordinator)
receives exam marks files — an "Advance" test and a "Mains" test — and today
works out by hand which marks belong to which student and sends each parent
their child's marks on WhatsApp.

The app removes that manual work: it reads the files, works out who each
student is, builds one WhatsApp message per student, lets the owner review and
approve everything, then helps send each message to the right parent and keeps
a record of what was sent.

**The overriding rule: one student's marks must never reach another student's
parent.** Accuracy beats speed everywhere. When the app is unsure, it stops and
asks the owner; it never guesses.

## 2. Goals, non-goals, anti-goals

**Goals**

- Import the owner's contact list (student name + parent WhatsApp number) from
  Excel, CSV or PDF, and keep it as a saved, editable list reused every round.
- Import one or more marks files per round (Excel, CSV, PDF; scanned PDFs via
  OCR as a fallback).
- Link every row in the marks files to the right student, with no wrong links:
  only certain matches are proposed automatically, everything else goes to the
  owner.
- Read Maths, Physics, Chemistry and Total; check them; handle negative marks,
  absentees (AB) and missing marks (NA).
- Build one message per student per round in the owner's format.
- Review and approve before anything is sent.
- Send by "phone mode" now (owner taps send in WhatsApp), and through the
  official WhatsApp Business Cloud API once the owner has set it up.
- Log every message: which student, which number, what text, when, how, result.
  Support retries and prevent duplicates.
- Keep every exam's marks per student for future cumulative reports.

**Non-goals (this version)**

- Cumulative / trend report screens (the data is kept so they can be added).
- Hosting online, several user accounts, or delivered/read ticks from the API
  (all three need an internet-facing server).
- Ranks, percentages or question-wise analysis in the message.

**Anti-goals — a failure even if everything else works**

- A message with one student's marks reaching another student's parent.
- A message containing more than one student's marks.
- A student record silently dropped: every row of every file and every contact
  must end up in a visible list (matched, needs review, not found, skipped).
- Missing marks treated as 0.
- Any message sent without the owner's approval, or as a side effect of upload.
- Unofficial WhatsApp automation (scripts driving WhatsApp Web, etc.).

## 3. Constraints

- **Stack (owner's choice):** Python, Streamlit, pandas + openpyxl, pdfplumber
  and/or PyMuPDF, Tesseract OCR, RapidFuzz, SQLite, WhatsApp Business Cloud API.
- **Runs on the owner's own computer.** Operating system not known — support
  Windows and macOS.
- **No WhatsApp Business API account today.**
- **The contact list has no STUD_ID today** — only names and numbers.
- **WhatsApp Cloud API rules (for stage 2):**
  - Messages the business starts must use a template approved by Meta.
  - Template variables cannot contain line breaks, tabs or more than four
    spaces in a row, so the multi-line layout must live in the template itself.
  - Meta charges per message; parents must have opted in.
  - Delivered/read status arrives only by webhook, which needs a public URL.

## 4. Approaches

| | Approach | Trade-off |
|---|---|---|
| A | **Phone mode only.** The app opens each parent's WhatsApp chat with the message pre-typed; the owner presses Send. | Works from round one, free, any format, no Meta setup. One click + one tap per student; app cannot confirm delivery. |
| **B** | **Phone mode first, official API added after.** *(Chosen.)* | Everything in the spec, usable immediately. More to build; once on the API: fixed approved templates, per-message fee, "accepted" rather than "delivered" status unless hosted. |
| — | API only | Ruled out: blocks all sending for the weeks Meta verification can take. |
| — | Unofficial WhatsApp Web automation | Ruled out by the owner: against WhatsApp's terms and risks the account. |

## 5. Decided by the owner

- Approach **B**.
- **Matching:** the first round matches by name with the owner confirming; the
  app then saves each student's STUD_ID against their contact. Later rounds
  match by STUD_ID with the name as a cross-check.
- **One message per student per round**, covering every exam uploaded in that
  round (Advance block, then Mains block).
- **Message layout** as in the owner's spec (section 6.8).
- **Absent students:** a student with no row in an exam's file is shown as AB
  for that exam and flagged for the owner to confirm. *(Proposed; owner did not
  object. To be re-checked against real files.)*
- Nothing is ever sent without review and approval.
- **Build against the samples already given:** the marks-file screenshot and
  the message preview image. No real files will be supplied before building.

## 6. Design

### 6.1 Where it runs and who can open it

- A Streamlit app on the owner's computer, opened in the browser.
- Listens on `127.0.0.1` only, so nobody else on the same Wi-Fi can open it.
- Password set on first run; only a salted hash is stored.
- All data in one SQLite file in a `data/` folder that is git-ignored.
- API credentials live in a local secrets file (not in the database, not in
  code). They are masked in the UI once entered.

### 6.2 What is stored (SQLite)

Exact schema is the builder's call; it must hold at least:

- **students** — display name, normalised name key, WhatsApp number (stored as
  `+91XXXXXXXXXX`), STUD_ID (nullable, unique), section, active flag, notes.
- **contact imports** — file name, file hash, time, row count.
- **rounds** — one per processing run (e.g. "Round of 17-Aug-2026").
- **exams** — raw test name, display name ("Advance Exam - 4"), type, number,
  test date, max marks per subject and total, source file and its hash, round.
- **marks** — per exam per file row: STUD_ID and name as written in the file,
  section, Maths / Physics / Chemistry / total-in-file / computed total (each
  value is a number, AB or NA), linked student (nullable until linked), issues.
- **ignored IDs** — STUD_IDs the owner marked "not my student".
- **messages** — round, student, number used, exact body, body hash, status,
  method (phone/API), API message id, error text, approved/opened/sent times,
  attempt count.
- **audit log** — time, action, details.

### 6.3 Importing the contact list

- Accepts `.xlsx`, `.xls`, `.csv`, `.pdf` (text PDF; OCR fallback).
- Detects the name and number columns from header words (name, student,
  whatsapp, mobile, phone, contact). The owner confirms the columns on the first
  import; the choice is remembered for files with the same headers.
- **Number clean-up:** strip spaces, dashes, brackets, a leading `0`, a `+91` or
  `91` prefix, and Excel's float form (`9.87654321E9`). A valid number is
  10 digits starting with 6–9, stored as `+91XXXXXXXXXX`. Anything else is
  flagged "Check number" and can be corrected in the app.
- **Duplicates:** the same cleaned name twice is flagged, never merged
  automatically. The same number on two students is a warning (probably
  siblings) and allowed once the owner confirms.
- **Re-uploading a newer list:** compared with the saved list, showing new
  students, changed numbers and students missing from the new file. The owner
  applies the changes. A row counts as an existing student only on an exact
  name-key match; anything else is shown as new for the owner to resolve.
  Students missing from the new file become inactive, never deleted.
- **Editing in the app:** name, number, STUD_ID link (unlink/relink), active.
  Every edit is audited.

### 6.4 Importing marks files

**Known layout** (from the owner's sample, test "JEE(Adv)/WTA-4"):

- Title "ALL INDIA MARKS ANALYSIS", then a header block with
  `Prog Name: …`, `Test Date: 17-August-2026`, `Test Name: JEE(Adv)/WTA-4`.
- Table columns: `STUD_ID`, `NAME OF THE STUDENT`, `SEC`, `TOT` (max 180), `%`,
  `AIR RANK`, `State Rank`, `Camp Rank`, `MAT` (max 60), `MAT RANK`, `%`,
  question lists (W, W_Q's, U, U_Q's), then the same for `PHY` and `CHE`.
- Max marks appear in the header cells under the subject labels (two-row
  header).
- Names are in capitals, surname first; long names wrap onto two lines.
- Negative subject marks occur (e.g. Chemistry −7, total 32 = 23 + 16 − 7).
- Several sections (PR3, PR4) in one file.

**Read:** STUD_ID, name, section, MAT, PHY, CHE, TOT, the max marks, Test Name,
Test Date. Ignore everything else.

**Readers**

- **Excel / CSV:** find the header row by locating the STUD_ID / NAME cells; map
  columns by keyword (MAT/MATHS, PHY/PHYSICS, CHE/CHEM, TOT/TOTAL); read max
  marks from the header; find Test Name and Test Date by their labels.
- **Text PDF:** pdfplumber table extraction page by page, joining wrapped name
  lines, then the same column mapping.
- **Scanned PDF (no text layer):** OCR with Tesseract. **Every row read by OCR
  is marked Needs Review and can never be approved in bulk.** If Tesseract is
  not installed, the app says so and rejects the file instead of guessing.
- On every upload the owner sees the detected columns, the exam name and the
  first few rows, and confirms them. Confirmed layouts are remembered by header
  signature. Unknown layouts can be mapped by hand.
- Every data row ends up either parsed or in an "unreadable rows" list with its
  raw text. The upload screen shows how many rows were read.

**Exam names**

- Rules in Settings turn the raw test name into the display name: a test name
  containing "Adv" becomes "Advance Exam", one containing "Main" becomes "Mains
  Exam", and the number is the last number in the test name
  ("JEE(Adv)/WTA-4" → "Advance Exam - 4"). The suggestion is shown at upload
  for the owner to confirm or edit.
- The Mains file is assumed to have the same layout with different max marks.
  If a real Mains file differs, the column-confirmation step at upload lets the
  owner map it by hand, and the mapping is remembered.
- **Duplicate exam:** a file with the same hash, or the same test name and date
  as one already imported, is blocked with a warning. The owner can choose to
  replace the earlier import.

**Rounds:** all files processed together form one round. Messages list exams
in the configured order (Advance, then Mains), then by number.

- Files can be added to or removed from a round until its first message is
  sent. Doing so re-processes the round and clears its approvals.
- After the first send, a late file starts a new round.

### 6.5 Matching engine

**Name key:** capitals, dots/commas/hyphens removed, spaces collapsed, words
sorted. "PALLAPU MEGHANA SRI" and "Meghana Sri Pallapu" give the same key.

For each row in the round's files:

1. **STUD_ID already linked to a student** → matched by ID. Cross-check the name
   in the file against the saved name (RapidFuzz token-sort similarity). If it
   falls below a threshold, the row needs review: "name differs from saved".
2. **STUD_ID not linked yet** → name matching against active students without a
   STUD_ID:
   - **Certain:** the name key is identical to exactly one student's, and no
     other row with a different STUD_ID in this round has the same key. The link
     is proposed.
   - **Possible:** fuzzy candidates above a floor score, including initials (a
     single letter matches a word starting with it: "V NIHARIKA DEVI" vs
     "Niharika Devi Vanga"). The row needs review, with the top candidates
     shown. The owner picks one or marks "not on my list".
   - **None:** the row goes on the Not found list.
3. **One-to-one:** a student can hold only one STUD_ID and a STUD_ID only one
   student. Any conflict needs review.
4. **The same STUD_ID across the round's files** must carry the same name; a
   mismatch needs review.
5. **New links are saved only after the owner confirms them.** All links
   proposed in a round — the certain ones included — are shown once as a list,
   and nothing is saved until the owner confirms.
6. **"Not my student"** remembers the STUD_ID. Future rounds show these rows in
   a collapsed "Not my students (N)" group, counted and never silent.
7. **A fuzzy score alone never links anyone.**

Thresholds are the builder's call. They must be tested against a list of
tricky Indian-name pairs: initials, surname-first order, spelling variants,
near-identical names of different students.

### 6.6 Marks processing and checks

- Each subject value is a number (negative allowed), **AB** (cell reads AB,
  ABSENT or A) or **NA** (blank, unreadable or anything else). Never 0 by
  default.
- **Range check:** value ≤ subject max, and value ≥ −(subject max) as a sanity
  floor. Outside that range → Needs Review.
- **Total:**
  - If all three subjects are numbers, the app computes the sum.
  - If the file's TOT differs from that sum, the student needs review with both
    numbers shown. The message cannot be approved until the owner picks one.
  - Any subject NA → total NA, needs review.
  - All three AB → total AB.
- **Absent:** a *linked* student (one with a saved STUD_ID) with no row in an
  exam's file gets AB for that whole exam and is flagged "Absent? confirm".
  This holds even when they are missing from every exam in the round. Their
  message is prepared with all AB and flagged, and the owner can skip it.
- **Unlinked and in no file this round** (e.g. a student whose name was never
  matched in round one): listed under "Not in any file". No message is
  prepared, because the app cannot tell "absent" from "name not recognised".
- The same STUD_ID appearing twice in one file needs review.

### 6.7 Statuses

Per student per round:

- **Ready** — linked with certainty, all values valid.
- **Needs Review** — with the list of reasons.
- **Not found** — a file row with no contact; no message.
- **Skipped** — by the owner.
- **Approved → Opened (phone mode) → Sent / Failed.**

A separate **Needs attention** page lists every issue with its reason.

**Safety rules**

- Any change after approval sends that student back to Needs Review: a contact
  number edit, a relink, or a marks correction.
- Just before sending, the message is rebuilt from the database and its hash
  compared with the approved one. If they differ, it is not sent.

### 6.8 Message format

The default layout, configurable in Settings as a template with placeholders.
Exam blocks repeat per exam in the round:

```
*Advance Exam - 4 Marks*

Maths - 41
Physics - 32
Chemistry - 17

*Total Marks - 90*

*Mains Exam - 4 Marks*

Maths - 62
Physics - 17
Chemistry - 16

*Total Marks - 95*
```

- The exam heading and total lines are bold. This is my reading of the owner's
  preview image, where those lines are emphasised.
- Negative marks are shown as `-7`; AB and NA are shown as text.
- The body is built from one student's records only.
- **Student name line:** a Settings switch, "Start each message with the
  student's name", **off by default** so the owner's format is kept exactly.
  The Contacts page warns when two students share a WhatsApp number (siblings)
  and suggests turning it on: without names, that parent cannot tell which
  message is which child's.

### 6.9 Sending — phone mode (stage 1)

- The **Send** page lists approved messages.
- Each row has an **Open in WhatsApp** link:
  `https://wa.me/<number without +>?text=<URL-encoded body>`.
  - Settings can switch it to WhatsApp Web (`web.whatsapp.com/send?...`) or the
    desktop app (`whatsapp://send?...`).
- **Guided flow:** one student at a time, showing name, number and message.
  1. Open the chat.
  2. Press Send in WhatsApp.
  3. Back in the app, choose **Mark sent** or **Couldn't send**, which moves on
     to the next student.
- The app records the opened time, the sent time (owner-confirmed) and
  method = phone. The status reads "Sent (by you)", because the app cannot
  verify delivery.
- **Send all / send selected / send one / skip** all work through this flow.
- **Duplicates:** a message already sent this round shows "Already sent on …"
  and needs an explicit "send again" confirmation.

### 6.10 Sending — official API (stage 2)

**Settings:** Phone Number ID, WhatsApp Business Account ID, a permanent access
token, and the template name(s) and language. These are kept in the local
secrets file.

**How sending works**

- Sends through the Graph API messages endpoint with `type: template`, filling
  body parameters from the student's record.
- Template variables can't hold line breaks, so the layout lives in the
  template. There is one template per round shape: Advance + Mains, Advance
  only, Mains only.
- The app picks the template matching the round's exams. If none is
  configured for that shape, it refuses to send.
- **Send all approved / selected / one:** messages go out one at a time with a
  configurable pause. Sending stops on authentication or rate-limit errors.

**Statuses**

- An API message id is recorded as "Accepted by WhatsApp".
- Errors are recorded as Failed with the error text. Failed messages can be
  retried.

**Crash safety**

- The status is written as "sending" before each call and updated after it.
- After a crash, any "sending" rows show as "Unknown — check" and are never
  resent automatically.

**Delivered/read ticks:** not in this version (they need webhook hosting).

**Setup guide** (written for the owner):

- Meta Business account and business verification.
- WhatsApp Business Account, phone number and display name.
- Payment method.
- Submitting the template texts (provided in the guide). They must not start
  or end with a variable, so they end with a fixed sign-off line.
- Creating a permanent token.
- Collecting parents' opt-in.

**Testing:** development uses Meta's free test number, which can send to up to
5 verified recipients.

### 6.11 History, audit and reports

- All marks rows are kept permanently. Each student's page shows every past
  exam.
- The messages table is the send log, including the number used at send time.
- The audit log covers imports, links made or changed, approvals, sends,
  contact edits and settings changes.
- **Round delivery report:** counts and lists of Sent, Failed, Pending and
  Skipped. It can be exported to Excel.

### 6.12 Screens

1. **Login.**
2. **Contacts:**
   - upload or re-upload, with a change summary
   - search and edit
   - issues: bad numbers, duplicates
3. **New round:**
   - upload one or more marks files
   - confirm columns and exam names per file
   - **Process**
4. **Needs attention:**
   - links to confirm
   - rows that need review
   - Not found
   - Not in any file
5. **Preview & approve:** the table below. Click a row to see the exact
   message. Approve all Ready, approve selected, skip.
6. **Send:** phone mode (guided flow) or API mode (bulk), and retry failed.
7. **Reports & history:** round reports, per-student history, audit log.
8. **Settings:**
   - password
   - message template and exam naming rules
   - send method and link type
   - API credentials

```
Round: 17-Aug-2026   (Advance Exam - 4, Mains Exam - 4)
┌──────────────────────────┬───────────────┬─────┬─────┬──────────────┐
│ Student                  │ WhatsApp      │ Adv │ Mns │ Status       │
├──────────────────────────┼───────────────┼─────┼─────┼──────────────┤
│ Pallapu Meghana Sri      │ +91 98765 4…  │  90 │  95 │ Ready        │
│ Gorantla Sai Karthik     │ +91 98765 4…  │  87 │ AB  │ Needs Review │
│ V Niharika Devi          │ —             │  27 │  64 │ Needs Review │
└──────────────────────────┴───────────────┴─────┴─────┴──────────────┘
[Approve all Ready]  [Approve selected]  [Skip selected]
```

## 7. Build order

Each stage is tested on its own before the next one is built.

1. **Core, usable for real rounds:**
   - storage, password, contacts import and editing
   - marks readers for Excel, CSV and text PDF (the real format is not known,
     so all three are in the core)
   - matching, marks checks, message building
   - review and approval
   - phone-mode sending, logs, reports
2. **OCR fallback** for scanned PDFs.
3. **Official API sending**, plus the Meta setup guide.
4. *(Later)* Cumulative performance reports.

**Testing**

- Unit tests per module, using fixture files generated to copy the screenshot
  layout with made-up names:
  - the title and header block
  - the two-row header with max marks
  - wrapped names, negative marks, two sections, the extra rank and question
    columns
  - each in Excel, CSV and text-PDF form, plus a Mains variant with different
    max marks
- A contact-list fixture with `Student Name` and `WhatsApp Number` columns, as
  in the spec. It includes messy numbers, a duplicate name and a shared sibling
  number.
- A name-matching test set of tricky pairs.
- An end-to-end test that asserts:
  - every input row and contact ends up in exactly one visible list
  - each message contains only its own student's values
  - nothing is sent without approval

## 8. Left to the builder

- Exact schema, module layout, fuzzy thresholds, password hashing method.
- PDF library choice per file (pdfplumber vs PyMuPDF).
- Streamlit page structure and widgets.
- Pause length between API sends.
- Install instructions for Windows and macOS (including optional Tesseract).

## 9. Calls made without the owner (check these)

- Student name line is a setting, off by default, with a warning when siblings
  share a number.
- File readers are built from the screenshot. The Mains file is assumed to
  match the Advance layout, and the contact list to have a name column and a
  number column.

- Runs on `127.0.0.1` only, with a single password; no database encryption.
  Disk encryption on the computer is recommended instead.
- Contact numbers are assumed to be Indian mobiles (+91); anything else is
  flagged.
- On every upload, the column mapping and exam name are shown for
  confirmation.
- Round-one links, the certain ones included, are confirmed once as a list
  before being saved.
- OCR-read rows always need individual review.
- A file total that differs from the computed total blocks approval until the
  owner picks one.
- A linked student absent from every exam in the round still gets a message
  prepared with AB, flagged for review; the owner can skip it.
- Files can be added to a round until its first message is sent; after that, a
  late file starts a new round.
- One WhatsApp number per student, as in the spec. A second number column, if
  present, is ignored.
- A student whose contact number changes after approval goes back to review.
- Students missing from a newer contact list become inactive, never deleted.
