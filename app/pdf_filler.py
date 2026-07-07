"""Fill the user's *own* uploaded PDF/image — instead of generating a new one.

Two strategies, decided at runtime:

1. AcroForm path — the upload already has interactive form fields. We set their
   values directly with `pypdf` (reliable, pixel-perfect, no coordinates needed).
2. Overlay path — the upload is a flat / scanned form with no fields. We draw the
   collected values on top of the original page at absolute coordinates (supplied
   by the caller, typically from Gemini vision) using `fpdf2`, then merge that
   transparent layer back onto the original with `pypdf`.

This module is intentionally free of ADK / LLM / network imports so it stays pure
and unit-testable. Heavy PDF libraries (`pypdf`, `fitz`) are imported lazily inside
the functions that need them, so importing this module stays cheap — important
because the MCP stdio server (`mcp_server.py`) imports the font helper at load time
and a heavy C-extension import there can deadlock the stdio JSON-RPC transport.
"""

from __future__ import annotations

import io
import os

# Fonts that support Indic / Unicode scripts, tried in order. Falls back to a
# built-in Latin font if none are present. Shared with mcp_server.py so the
# data-sheet fallback and the overlay path render native scripts identically.
UNICODE_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\Nirmala.ttc",   # Windows 11: Nirmala UI collection — Devanagari, Tamil, Telugu, etc.
    r"C:\Windows\Fonts\Nirmala.ttf",   # older Windows layout (single-file variant)
    r"C:\Windows\Fonts\mangal.ttf",    # Devanagari
    r"C:\Windows\Fonts\ARIALUNI.TTF",  # Arial Unicode MS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def register_unicode_font(pdf) -> bool:
    """Register the first available Unicode font on an FPDF instance as "uni".

    Returns True if a Unicode font was registered (so native-language values will
    render), False if we must fall back to the built-in Latin font "helvetica".
    """
    for path in UNICODE_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                pdf.add_font("uni", "", path)
                pdf.add_font("uni", "B", path)
                return True
            except Exception:
                continue
    return False


# --------------------------------------------------------------------------- #
# Input normalisation
# --------------------------------------------------------------------------- #
def image_to_pdf_bytes(image_bytes: bytes) -> bytes:
    """Wrap a raw image into a single-page PDF so it can be overlaid.

    PyMuPDF sniffs PNG/JPEG straight from the byte stream, but cannot always
    detect other raster formats (WebP in particular) with no filetype hint, so we
    fall back to Pillow — which decodes webp/tiff/bmp/gif reliably — and re-encode
    to PNG before handing the bytes back to fitz. This keeps the fast native path
    for the common cases while accepting any format Pillow can open.
    """
    import fitz  # PyMuPDF — lazy import (heavy C-extension)

    try:
        doc = fitz.open(stream=image_bytes, filetype=None)  # infer type from bytes
    except Exception:
        # fitz could not detect the format — normalise via Pillow to PNG bytes.
        import io

        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
        doc = fitz.open(stream=buf.getvalue(), filetype="png")

    try:
        return doc.convert_to_pdf()
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# AcroForm (interactive fields) path
# --------------------------------------------------------------------------- #
def has_acroform_fields(pdf_bytes: bytes) -> bool:
    """True if the PDF has interactive AcroForm fields we can fill directly."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        fields = reader.get_fields()
    except Exception:
        return False
    return bool(fields)


def list_acroform_fields(pdf_bytes: bytes) -> list[str]:
    """Return the fully-qualified names of every AcroForm field in the PDF."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    fields = reader.get_fields() or {}
    return list(fields.keys())


def fill_acroform(pdf_bytes: bytes, mapping: dict[str, str]) -> bytes:
    """Set AcroForm field values and return the filled PDF as bytes.

    `mapping` is {field_name: value}. Unknown field names are ignored by pypdf.
    NeedAppearances is enabled so viewers regenerate the visible text.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)

    # Only pass string values; drop blanks so we never clobber a field with "".
    clean = {k: str(v) for k, v in mapping.items() if v not in (None, "")}
    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, clean, auto_regenerate=False)
        except Exception:
            # A page without widgets raises in some pypdf versions — skip it.
            continue

    try:
        writer.set_need_appearances_writer(True)
    except Exception:
        pass

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Overlay (flat / scanned) path
# --------------------------------------------------------------------------- #
def page_sizes(pdf_bytes: bytes) -> list[tuple[float, float]]:
    """Return (width, height) in PDF points for every page."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [(p.rect.width, p.rect.height) for p in doc]
    finally:
        doc.close()


def extract_line_anchors(pdf_bytes: bytes) -> list[dict]:
    """Deterministically locate each blank/underline and the label before it.

    For a *text-based* (not scanned) form this is far more reliable than asking a
    vision model for coordinates: we read the real geometry. Crucially, anchors
    are at BLANK-RUN granularity, not line granularity — a single dense line like
    "Tel.: ___ Mobile No.: ___ Fax: ___ Email id: ___" yields four separate
    anchors, each labelled by the words immediately before its blank, so multiple
    fields on one line never collide.

    Each anchor is {"index", "page", "label", "x", "y"} where (x, y) is the point
    — in PDF points from the TOP-LEFT — at which the value should be written (the
    start of the blank, on that line's baseline). Returns [] for pages with no
    extractable text (scanned images), signalling the vision fallback is needed.
    """
    import re

    import fitz

    blank_re = re.compile(r"^[_\.․‥…]{2,}$")  # underscore / dot-leader runs
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    anchors: list[dict] = []
    try:
        for pno, page in enumerate(doc):
            # words: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            words = page.get_text("words")
            lines: dict[tuple, list] = {}
            for w in words:
                lines.setdefault((w[5], w[6]), []).append(w)

            for _key, ws in lines.items():
                ws.sort(key=lambda t: t[0])
                y = max(t[3] for t in ws) - 1  # baseline ≈ bottom of the line box
                label_buf: list[str] = []
                prev_blank = False
                emitted = False
                for t in ws:
                    word = t[4]
                    if blank_re.match(word):
                        if not prev_blank:  # first blank of a run → one anchor
                            label = " ".join(label_buf[-8:]).strip()
                            if label:
                                anchors.append(
                                    {
                                        "index": len(anchors),
                                        "page": pno,
                                        "label": label,
                                        "x": float(t[0]),
                                        "y": float(y),
                                    }
                                )
                                emitted = True
                            label_buf = []  # label belongs only to this blank
                        prev_blank = True
                    else:
                        label_buf.append(word)
                        prev_blank = False

                # Line with a label but no visible underline (e.g. "Label:" then
                # empty space) — place just after the label so it still fills.
                if not emitted:
                    label = " ".join(label_buf).strip()
                    if label.endswith(":") and len(label) > 1:
                        anchors.append(
                            {
                                "index": len(anchors),
                                "page": pno,
                                "label": label,
                                "x": float(max(t[2] for t in ws) + 4),
                                "y": float(y),
                            }
                        )
    finally:
        doc.close()
    return anchors


def _split_comb_groups(cells: list[tuple]) -> list[list[tuple]]:
    """Split a row of x-sorted cells into separate comb fields at large gaps."""
    if not cells:
        return []
    cell_w = cells[0][2] - cells[0][0]
    groups = [[cells[0]]]
    for prev, cur in zip(cells, cells[1:]):
        # A gap wider than ~2.8 cells means a new field (not a within-field space).
        if (cur[0] - prev[0]) > 2.8 * max(cell_w, 1):
            groups.append([cur])
        else:
            groups[-1].append(cur)
    return groups


def _label_for_cells(words: list, cells: list[tuple]) -> str:
    """Best-guess label for a comb field: text to its left, else the line above."""
    x0 = cells[0][0]
    y_top = min(c[1] for c in cells)
    y_bot = max(c[3] for c in cells)
    y_mid = (y_top + y_bot) / 2

    # Prefer words on the same row, to the left of the first cell.
    left = [w for w in words if w[2] <= x0 + 2 and y_top - 3 <= (w[1] + w[3]) / 2 <= y_bot + 3]
    if left:
        left.sort(key=lambda w: w[0])
        return " ".join(w[4] for w in left[-8:]).strip()

    # Otherwise the nearest text line directly above the field.
    above = [w for w in words if w[3] <= y_mid and cells[0][0] - 40 <= w[0] <= cells[-1][2] + 40]
    if above:
        above.sort(key=lambda w: w[3])
        band_bottom = above[-1][3]
        band = [w for w in above if band_bottom - w[3] <= 6]
        band.sort(key=lambda w: w[0])
        return " ".join(w[4] for w in band[-8:]).strip()
    return ""


def extract_box_rows(pdf_bytes: bytes, min_cells: int = 4) -> list[dict]:
    """Detect comb/box grids (one character per cell) drawn as vector rectangles.

    Government KYC forms often use a row of small equal squares instead of an
    underline. Each returned row is {"index", "page", "label", "cells"} where
    cells is the ordered list of (x0, y0, x1, y1) cell rectangles in PDF points
    from the top-left, so a value can be written one character per box.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rows_out: list[dict] = []
    try:
        for pno, page in enumerate(doc):
            seen: set = set()
            cells: list[tuple] = []
            for d in page.get_drawings():
                for item in d["items"]:
                    if item[0] != "re":
                        continue
                    r = item[1]
                    w, h = r.width, r.height
                    if 8 <= w <= 16 and 8 <= h <= 22:  # comb-cell size range
                        key = (round(r.x0), round(r.y0))
                        if key not in seen:
                            seen.add(key)
                            cells.append((float(r.x0), float(r.y0), float(r.x1), float(r.y1)))
            if not cells:
                continue

            # Group cells into rows by y (tolerance ~3pt), then split each row
            # into distinct comb fields at large horizontal gaps.
            rows: dict[int, list] = {}
            for c in cells:
                rows.setdefault(round(c[1] / 3), []).append(c)

            words = page.get_text("words")
            for _yk, cs in rows.items():
                cs.sort(key=lambda c: c[0])
                for group in _split_comb_groups(cs):
                    if len(group) < min_cells:
                        continue
                    rows_out.append(
                        {
                            "index": len(rows_out),
                            "page": pno,
                            "label": _label_for_cells(words, group),
                            "cells": group,
                        }
                    )
    finally:
        doc.close()
    return rows_out


def boxes_to_char_placements(row: dict, value: str, size: float = 9.0) -> list[dict]:
    """Expand a value into one-character-per-cell placements for a comb row.

    Block-letter forms expect uppercase; a space in the value advances one cell
    (leaving it blank) to mirror word separators. Returns standard overlay
    placements ({"page", "x", "y", "value", "size"}) with each character centred
    in its cell.
    """
    cells = row["cells"]
    page = row["page"]
    out: list[dict] = []
    ci = 0
    for ch in str(value).upper():
        if ci >= len(cells):
            break
        if ch == " ":
            ci += 1
            continue
        x0, y0, x1, y1 = cells[ci]
        char_w = 0.6 * size
        cx = x0 + max(0.0, (x1 - x0 - char_w) / 2)
        baseline = y1 - max(2.0, (y1 - y0) * 0.2)
        out.append({"page": page, "x": cx, "y": baseline, "value": ch, "size": size})
        ci += 1
    return out


def render_pages_to_pngs(pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
    """Render each page to a PNG (bytes) for vision-based coordinate mapping."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [page.get_pixmap(dpi=dpi).tobytes("png") for page in doc]
    finally:
        doc.close()


def overlay_values(pdf_bytes: bytes, placements: list[dict]) -> bytes:
    """Draw values onto the original PDF at absolute coordinates and return bytes.

    Each placement is {"page": int, "x": float, "y": float, "value": str} where
    x/y are in PDF points measured from the TOP-LEFT of the page (matching the
    convention Gemini vision returns), and page is a 0-based index.
    """
    from fpdf import FPDF
    from pypdf import PdfReader, PdfWriter

    sizes = page_sizes(pdf_bytes)
    if not sizes:
        return pdf_bytes

    # Build a transparent overlay document, one page per original page, same size.
    overlay = FPDF(unit="pt")
    overlay.set_auto_page_break(False)
    unicode_ok = register_unicode_font(overlay)
    font = "uni" if unicode_ok else "helvetica"

    def encode(value: str) -> str:
        if unicode_ok:
            return value
        return value.encode("latin-1", "replace").decode("latin-1")

    by_page: dict[int, list[dict]] = {}
    for p in placements:
        by_page.setdefault(int(p.get("page", 0)), []).append(p)

    for idx, (w, h) in enumerate(sizes):
        overlay.add_page(format=(w, h))
        overlay.set_text_color(0, 0, 0)
        for p in by_page.get(idx, []):
            value = str(p.get("value", "")).strip()
            if not value:
                continue
            x = max(0.0, min(float(p.get("x", 0)), w))
            y = max(0.0, min(float(p.get("y", 0)), h))
            overlay.set_font(font, "", float(p.get("size", 11)))
            # FPDF.text places the baseline at (x, y) from the top-left — same
            # origin the caller uses — so the merged layers line up.
            overlay.text(x, y, encode(value))

    overlay_bytes = bytes(overlay.output())

    # Merge the overlay onto the original, page by page. Clone the original into
    # the writer first so pages are writer-attached before merge (pypdf's
    # reliable path — merging detached reader pages is deprecated/unreliable).
    writer = PdfWriter(clone_from=io.BytesIO(pdf_bytes))
    over = PdfReader(io.BytesIO(overlay_bytes))
    for i, page in enumerate(writer.pages):
        if i < len(over.pages):
            page.merge_page(over.pages[i])

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
