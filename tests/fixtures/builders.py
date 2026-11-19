"""Made-up sample data and file writers that copy the owner's marks-file layout.

These are the only student names allowed in the repository: all invented.
"""
from __future__ import annotations

import csv
from pathlib import Path

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
MAINS_ROWS = [(i, n, s, m + 20, p + 10, c + 5, t + 35) for i, n, s, m, p, c, t in SAMPLE_ROWS]

CONTACTS = [  # name, number as typed
    ("Meghana Sri Pallapu", "98765 43201"), ("Gorantla Sai Kartik", "+91 98765-43202"),
    ("Muddana Venkata Sai Srinivas Rao", "9876543203"), ("Niharika Devi Vanga", "09876543204"),
    ("Nakka Ravi Teja", "9876543205"), ("Nakka Ravi Kiran", "9876543205"),  # siblings share
    ("Kolluri Anjali", "98765432"), ("Syed Afreen", 9876543208.0),  # bad number; float
]

WIDTH = 29
HEADER_1 = ["STUD_ID", "NAME OF THE STUDENT", "SEC", "TOT", "%", "AIR RANK", "State Rank",
            "Camp Rank", "MAT", "MAT RANK", "%", "Mat_Q's", "", "", "", "PHY", "PHY RANK", "%",
            "Phy_Q's", "", "", "", "CHE", "CHE RANK", "%", "Che_Q's", "", "", ""]
Q_SUB = ["W", "W_Q's", "U", "U_Q's"]


def _pad(row: list) -> list:
    return list(row) + [""] * (WIDTH - len(row))


def _header_2(maxes) -> list:
    m, p, c, t = maxes
    return ["", "", "", t, "", "", "", "", m, "", "", *Q_SUB, p, "", "", *Q_SUB, c, "", "", *Q_SUB]


def _data_row(i: int, r, maxes) -> list:
    sid, name, sec, m, p, c, t = r
    mm, pm, cm, tm = maxes
    pct = lambda v, mx: round(v * 100 / mx, 1)
    qs = lambda k: [k % 9, f"Q{40 + k},Q{41 + k}", k % 5, f"Q{50 + k}"]
    return [int(sid), name, sec, t, pct(t, tm), 40 + i * 7, 26 + i * 4, i + 1,
            m, 25 + i, pct(m, mm), *qs(i), p, 64 + i, pct(p, pm), *qs(i + 1),
            c, 104 + i, pct(c, cm), *qs(i + 2)]


def marks_grid(test_name="JEE(Adv)/WTA-4", test_date="17-August-2026", maxes=(60, 60, 60, 180),
               rows=SAMPLE_ROWS, footer=None, repeat_header_after=None) -> list[list]:
    grid = [_pad(["ALL INDIA MARKS ANALYSIS"]), _pad(["Prog Name:", "Sample Programme"]),
            _pad(["Test Date:", test_date]), _pad(["Test Name:", test_name]),
            list(HEADER_1), _header_2(maxes)]
    for i, r in enumerate(rows):
        if repeat_header_after is not None and i == repeat_header_after:
            grid += [list(HEADER_1), _header_2(maxes)]
        grid.append(_data_row(i, r, maxes))
    if footer:
        grid.append(_pad([footer]))
    return grid


def write_xlsx(grid, path, merge_headers=False) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for row in grid:
        ws.append([None if v == "" else v for v in row])
    if merge_headers:
        h1 = next(i for i, row in enumerate(grid, start=1) if row and row[0] == "STUD_ID")
        for col in (1, 2, 3):  # STUD_ID, NAME, SEC span both header rows
            ws.merge_cells(start_row=h1, start_column=col, end_row=h1 + 1, end_column=col)
        for start in (12, 19, 26):  # each *_Q's label spans its 4 sub-columns
            ws.merge_cells(start_row=h1, start_column=start, end_row=h1, end_column=start + 3)
    wb.save(path)


def write_csv(grid, path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(grid)


def write_pdf(grid, path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=6, leading=7)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=9, leading=11)
    h1 = next(i for i, row in enumerate(grid) if row and row[0] == "STUD_ID")
    story = [Paragraph(" ".join(str(c) for c in row if c != ""), head) for row in grid[:h1]]
    story.append(Spacer(1, 6))
    rows = []
    for row in grid[h1:]:
        out = [str(v) for v in row]
        if row[0] == "STUD_ID":  # header labels wrap inside their cells, like the real file
            out = [Paragraph(v, cell) if v else "" for v in out]
        else:
            out[1] = Paragraph(out[1], cell)  # long names wrap onto two lines
        rows.append(out)
    widths = [48, 70, 22] + [26] * (WIDTH - 3)
    table = Table(rows, colWidths=widths)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black),
                               ("FONTSIZE", (0, 0), (-1, -1), 6),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(table)
    SimpleDocTemplate(str(path), pagesize=landscape(A3), leftMargin=20, rightMargin=20).build(story)


def write_blank_pdf(path) -> None:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    c.rect(100, 100, 200, 100, fill=1)  # an image-like page with no text
    c.save()


def write_contacts_xlsx(path, rows=CONTACTS) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Student Name", "WhatsApp Number"])
    for name, number in rows:
        ws.append([name, number])
    wb.save(path)


def write_all_marks_files(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    adv = marks_grid()
    mains = marks_grid(test_name="JEE(Main)/WTM-4", maxes=(100, 100, 100, 300), rows=MAINS_ROWS)
    files = {"xlsx": folder / "adv4.xlsx", "csv": folder / "adv4.csv", "pdf": folder / "adv4.pdf",
             "mains_xlsx": folder / "mains4.xlsx", "mains_pdf": folder / "mains4.pdf"}
    write_xlsx(adv, files["xlsx"])
    write_csv(adv, files["csv"])
    write_pdf(adv, files["pdf"])
    write_xlsx(mains, files["mains_xlsx"])
    write_pdf(mains, files["mains_pdf"])
    return files
