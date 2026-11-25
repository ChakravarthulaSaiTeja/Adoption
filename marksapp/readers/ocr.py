"""Read a scanned PDF (pictures of pages, no text layer) with Tesseract OCR.

Marks sheets are ruled tables, so the table's grid lines are found in the image
and used as cell boundaries; they are then erased so they don't confuse the OCR,
and every recognised word is placed in the cell it sits in. Without a grid, words
are split into cells by the gaps between them.

OCR makes mistakes, so every student read this way must be checked one by one
(results.py adds an 'ocr' issue and approve() never bulk-approves them).
"""
from __future__ import annotations

import io
import statistics

from marksapp.readers.grid import Grid

DPI = 300
DARK = 128


def ocr_available() -> bool:
    try:
        import pymupdf  # noqa: F401
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _runs(mask) -> list[int]:
    """Centres of consecutive True runs in a 1-D boolean array."""
    centres, start = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            centres.append((start + i - 1) // 2)
            start = None
    return centres


def _grid_lines(dark) -> tuple[list[int], list[int]]:
    """Horizontal and vertical ruling lines (pixel positions) of the table, if any."""
    import numpy as np
    h, w = dark.shape
    horizontal = _runs(dark.mean(axis=1) > 0.5)
    if len(horizontal) < 3:
        return [], []
    top, bottom = horizontal[0], horizontal[-1]
    vertical = _runs(dark[top:bottom + 1].mean(axis=0) > 0.8)
    if len(vertical) < 3:
        return [], []
    return horizontal, vertical


def _erase(gray, horizontal, vertical, half: int = 3):
    img = gray.copy()
    top, bottom = horizontal[0], horizontal[-1]
    left, right = vertical[0], vertical[-1]
    for y in horizontal:
        img[max(0, y - half):y + half + 1, left:right + 1] = 255
    for x in vertical:
        img[top:bottom + 1, max(0, x - half):x + half + 1] = 255
    return img


def _words(image) -> list[dict]:
    import pytesseract
    d = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config="--psm 6")
    out = []
    for i, text in enumerate(d["text"]):
        text = text.strip().strip("|").strip()
        if text:
            out.append({"text": text, "left": d["left"][i], "top": d["top"][i], "width": d["width"][i],
                        "height": d["height"][i],
                        "line": (d["block_num"][i], d["par_num"][i], d["line_num"][i])})
    return out


def _gap_rows(words: list[dict]) -> list[list[str]]:
    lines: dict[tuple, list[dict]] = {}
    for w in words:
        lines.setdefault(w["line"], []).append(w)
    rows = []
    for key in sorted(lines, key=lambda k: min(w["top"] for w in lines[k])):
        ws = sorted(lines[key], key=lambda w: w["left"])
        gap_limit = 1.5 * statistics.median(w["height"] for w in ws)
        cells, current, last_right = [], [], None
        for w in ws:
            if last_right is not None and w["left"] - last_right > gap_limit:
                cells.append(" ".join(current))
                current = []
            current.append(w["text"])
            last_right = w["left"] + w["width"]
        cells.append(" ".join(current))
        rows.append(cells)
    return rows


def _between(edges: list[int], v: float) -> int | None:
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]:
            return i
    return None


def _page_grid(gray) -> Grid:
    import numpy as np
    from PIL import Image
    horizontal, vertical = _grid_lines(gray < DARK)
    if not horizontal:
        return _gap_rows(_words(Image.fromarray(gray)))
    words = _words(Image.fromarray(_erase(gray, horizontal, vertical)))
    above = [w for w in words if w["top"] + w["height"] / 2 < horizontal[0]]
    rows: Grid = _gap_rows(above)
    cells = [[[] for _ in range(len(vertical) - 1)] for _ in range(len(horizontal) - 1)]
    for w in words:
        r = _between(horizontal, w["top"] + w["height"] / 2)
        c = _between(vertical, w["left"] + w["width"] / 2)
        if r is not None and c is not None:
            cells[r][c].append(w)
    for row in cells:
        rows.append([" ".join(w["text"] for w in sorted(cell, key=lambda w: (w["top"] // 10, w["left"])))
                     for cell in row])
    return rows


def ocr_pdf_to_grid(data: bytes) -> Grid:
    import numpy as np
    import pymupdf
    from PIL import Image
    grid: Grid = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=DPI)
            gray = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("L"))
            grid += _page_grid(gray)
    return grid
