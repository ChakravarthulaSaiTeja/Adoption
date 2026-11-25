# Marks to Parents

Send each student's exam marks to their own parent on WhatsApp, every two weeks,
with you checking everything before anything is sent.

## What it does

1. Keeps your **contact list**: student names and parents' WhatsApp numbers.
2. Reads the **marks files** you upload (Excel, CSV or PDF), for example the
   Advance and the Mains file of a round.
3. Works out **which student each row belongs to**:
   - In the first round it matches by name and asks you to confirm.
   - After that it recognises each student by the ID in the marks file
     (`STUD_ID`).
   - When it isn't sure, it asks you. It never guesses.
4. Checks the marks:
   - absent shows as **AB**, missing shows as **NA** (never 0)
   - negative marks are allowed
   - totals are checked against the subjects
5. Builds **one message per student**, in your format:

   ```
   *Advance Exam - 4 Marks*

   Maths - 41
   Physics - 32
   Chemistry - 17

   *Total Marks - 90*
   ```

6. Lets you **preview and approve** every message.
7. Helps you **send** each approved message from your own WhatsApp: it opens
   the chat with the message already typed, and you press Send.
8. Keeps a **record** of what was sent, to which number and when, and every
   student's marks from every round.

**The most important rule:** a message is only ever built from one student's
own marks, and it is sent only if the number and the text are still exactly
what you approved.

## Install (once)

You need **Python 3.10 or newer**. Get it from <https://www.python.org/downloads/>.
On Windows, tick "Add Python to PATH" while installing.

Open a terminal (Windows: *Command Prompt*; Mac: *Terminal*) in this folder and run:

```
python -m venv .venv
```

Then activate it:

```
# Windows
.venv\Scripts\activate
# Mac
source .venv/bin/activate
```

Then install:

```
pip install -r requirements.txt
```

### Optional: reading scanned PDFs

If a marks PDF is a scan (a picture of the table), the app can read it with
**Tesseract OCR**, but only if Tesseract is installed:

- **Windows:** install it from <https://github.com/UB-Mannheim/tesseract/wiki>,
  then restart the terminal.
- **Mac:** `brew install tesseract`

OCR makes mistakes (a lost minus sign, a misread digit). Every student read from
a scanned PDF must be checked and approved one by one; the app never approves
them in bulk. Ask for the Excel file whenever you can.

## Start it

Each time, open a terminal in this folder, activate as above, then run:

```
streamlit run app.py
```

Your browser opens at <http://localhost:8501>. The app only listens on your
own computer: nobody else on your Wi-Fi can open it.

**First run:** choose a password (at least 8 characters). You'll need it every
time you open the app.

## Every two weeks

1. **Contacts** — upload the contact list if it changed.
   - The app shows you what changed before applying anything: new students,
     changed numbers, students who will become inactive.
   - Bad numbers and repeated names are listed for you to fix.
2. **New round** — upload this round's marks files (Advance and Mains).
   - Check the exam name and the first rows the app read, then press
     **Add to round**.
3. **Needs attention**
   - Confirm which student each file row belongs to. The first round takes a
     few minutes; later rounds are mostly automatic.
   - Fix any marks problems shown in red.
4. **Preview & approve** — look at the messages.
   - **Approve all Ready** approves every student with no problems.
   - Students that need a look are approved one by one, after you've checked
     them.
5. **Send** — one student at a time:
   1. Press **Open in WhatsApp**.
   2. Press Send in WhatsApp.
   3. Come back and press **✅ Sent**.
6. **Reports & history** — see what was sent, what failed and what's pending,
   and download it as Excel.

Nothing is ever sent just because you uploaded a file.

## Settings

- **Message format**: change the text around the marks. Words between `*stars*`
  show in bold on WhatsApp.
- **Start each message with the student's name**: turn this on if brothers or
  sisters share a parent's number. The Contacts page warns you when that
  happens.
- **Exam names**: which words in a test name mean "Advance Exam" or "Mains
  Exam", and their order in the message.
- **How WhatsApp opens**: WhatsApp link, WhatsApp Web, or the desktop app.

## Your data

- Everything is stored in the `data` folder next to the app.
- **Back it up** by copying that folder somewhere safe.
- It holds students' marks and parents' numbers. Never share it, and keep your
  computer's disk encryption on (Windows: BitLocker; Mac: FileVault).

## Troubleshooting

- **"This PDF is a scanned image and OCR is not installed"**: the PDF is a photo
  of the table, not real text. Install Tesseract (see above), or ask for the
  Excel file or a normal PDF export.
- **"Couldn't find the marks table"**: the file's headers look different from
  usual.
  - Choose the columns by hand on the New round page.
  - The app remembers your choice for files with the same headers.
- **"Messages changed since approval"**: a number or a mark changed after you
  approved. Approve those students again on Preview & approve.
- **A student shows "Not found on your list"**: link them by hand on Needs
  attention, or mark them "Not my student".

## For developers

```
pip install -r requirements-dev.txt
pytest
```

The design is in `docs/superpowers/specs/` and the build plan in
`docs/superpowers/plans/`. Tests only ever use made-up students.
