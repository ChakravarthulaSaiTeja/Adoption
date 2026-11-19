import io

import openpyxl

from marksapp.messages import message_settings
from marksapp.outbox import approve, get_outbox, mark_failed, mark_sent, skip
from marksapp.reports import message_log, report_xlsx, round_counts, round_report, student_history
from tests.helpers import linked_round


def test_counts_and_report(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    ids = approve(conn, rid, rr.students, message_settings(conn))
    out = get_outbox(conn, rid)
    mark_sent(conn, out[ids[0]].id)
    mark_failed(conn, out[ids[1]].id, "Number not on WhatsApp")
    skip(conn, rid, [ids[2]])
    c = round_counts(conn, rid)
    assert c["Sent"] == 1 and c["Failed"] == 1 and c["Skipped"] == 1
    assert c["Pending"] == len(rr.students) - 3
    df = round_report(conn, rid)
    assert list(df.columns) == ["Student", "WhatsApp", "Status", "Method", "Sent at", "Attempts", "Error"]
    assert len(df) == len(rr.students)
    assert "Number not on WhatsApp" in set(df["Error"])
    wb = openpyxl.load_workbook(io.BytesIO(report_xlsx(df)))
    assert wb.active.max_row == len(df) + 1


def test_history(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    s = next(x for x in rr.students if x.name == "Muddana Venkata Sai Srinivas Rao")
    h = student_history(conn, s.student_id)
    assert list(h.columns) == ["Round", "Exam", "Test date", "Maths", "Physics", "Chemistry", "Total"]
    assert list(h["Exam"]) == ["Advance Exam - 4", "Mains Exam - 4"]
    assert h.iloc[0]["Chemistry"] == "-7" and h.iloc[0]["Total"] == "32"


def test_message_log(conn, tmp_path):
    rid, rr = linked_round(conn, tmp_path)
    [sid] = approve(conn, rid, [s for s in rr.students if s.status == "ready"][:1], message_settings(conn))
    mark_sent(conn, get_outbox(conn, rid)[sid].id)
    log = message_log(conn, sid)
    assert list(log.columns) == ["Round", "Status", "WhatsApp", "Method", "Sent at", "Message"]
    assert log.iloc[0]["Status"] == "Sent"
