"""Turn an uploaded Excel, CSV or PDF file into a plain grid of text cells."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from pathlib import Path

Grid = list[list[str]]

_INT = re.compile(r"^\d+$")
_INT_DOT_ZERO = re.compile(r"^(\d+)\.0+$")
_SCIENTIFIC = re.compile(r"^\d+(\.\d+)?[eE]\+?\d+$")


class UnsupportedFile(Exception):
    pass


class NoTextInPdf(Exception):
    """The PDF has no text layer (a scanned image)."""


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, int):
        return str(v)
    return " ".join(str(v).split())


cell_text = _cell


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_id(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, float):
        if math.isnan(raw):
            return ""
        if raw.is_integer():
            return str(int(raw))
    if isinstance(raw, int) and not isinstance(raw, bool):
        return str(raw)
    s = str(raw).strip()
    if _INT.match(s):
        return str(int(s))
    m = _INT_DOT_ZERO.match(s)
    if m:
        return str(int(m.group(1)))
    if _SCIENTIFIC.match(s):
        f = float(s)
        if f.is_integer():
            return str(int(f))
    return s


def _excel(data: bytes, engine: str) -> Grid:
    import pandas as pd
    df = pd.read_excel(io.BytesIO(data), header=None, dtype=object, engine=engine)
    return [[_cell(v) for v in row] for row in df.itertuples(index=False, name=None)]


def _csv(data: bytes) -> Grid:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return [[_cell(v) for v in row] for row in csv.reader(io.StringIO(text))]


def _pdf(data: bytes) -> Grid:
    import pdfplumber
    grid: Grid = []
    any_text = False
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for index, page in enumerate(pdf.pages):
            if page.chars:
                any_text = True
            tables = page.find_tables()
            if index == 0:
                top = tables[0].bbox[1] if tables else page.height
                if top > 1:
                    above = page.crop((0, 0, page.width, top)).extract_text() or ""
                    grid += [[_cell(line)] for line in above.splitlines() if line.strip()]
            for table in tables:
                grid += [[_cell(v) for v in row] for row in table.extract()]
    if not any_text:
        raise NoTextInPdf("This PDF has no text layer")
    return grid


def load_grid(data: bytes, filename: str) -> Grid:
    ext = Path(filename).suffix.lower()
    if ext == ".xlsx":
        return _excel(data, "openpyxl")
    if ext == ".xls":
        return _excel(data, "xlrd")
    if ext == ".csv":
        return _csv(data)
    if ext == ".pdf":
        return _pdf(data)
    raise UnsupportedFile(f"Unsupported file type: {ext or filename}")


def grid_lines(grid: Grid) -> list[str]:
    return [" ".join(c for c in row if c) for row in grid]
