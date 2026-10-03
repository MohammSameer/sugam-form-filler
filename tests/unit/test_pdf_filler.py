"""Unit tests for the PDF filling engine (pure functions — no LLM / network)."""

import io

import pytest

from app import pdf_filler


def _make_acroform_pdf() -> bytes:
    """Build a tiny one-page PDF with a single text field named 'full_name'."""
    import fitz  # PyMuPDF has a clean, reliable widget-creation API

    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    widget = fitz.Widget()
    widget.field_name = "full_name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(20, 50, 280, 80)
    page.add_widget(widget)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def _make_flat_pdf() -> bytes:
    """A plain two-page PDF with no form fields."""
    from fpdf import FPDF

    pdf = FPDF(unit="pt")
    pdf.add_page(format=(300, 200))
    pdf.set_font("helvetica", "", 12)
    pdf.text(20, 40, "Name:")
    pdf.add_page(format=(300, 200))
    pdf.text(20, 40, "Signature:")
    return bytes(pdf.output())


def test_has_acroform_fields_true():
    assert pdf_filler.has_acroform_fields(_make_acroform_pdf()) is True


def test_has_acroform_fields_false():
    assert pdf_filler.has_acroform_fields(_make_flat_pdf()) is False


def test_list_acroform_fields():
    names = pdf_filler.list_acroform_fields(_make_acroform_pdf())
    assert "full_name" in names


def test_fill_acroform_roundtrips_value():
    from pypdf import PdfReader

    filled = pdf_filler.fill_acroform(_make_acroform_pdf(), {"full_name": "Asha Kumari"})
    fields = PdfReader(io.BytesIO(filled)).get_fields()
    assert fields["full_name"].get("/V") == "Asha Kumari"


def test_overlay_preserves_page_count_and_is_valid_pdf():
    from pypdf import PdfReader

    base = _make_flat_pdf()
    out = pdf_filler.overlay_values(
        base,
        [
            {"page": 0, "x": 60, "y": 40, "value": "Asha Kumari"},
            {"page": 1, "x": 90, "y": 40, "value": "AK"},
        ],
    )
    assert out.startswith(b"%PDF")
    assert len(PdfReader(io.BytesIO(out)).pages) == 2


def test_page_sizes():
    sizes = pdf_filler.page_sizes(_make_flat_pdf())
    assert len(sizes) == 2
    w, h = sizes[0]
    assert round(w) == 300 and round(h) == 200


def test_render_pages_to_pngs():
    pngs = pdf_filler.render_pages_to_pngs(_make_flat_pdf())
    assert len(pngs) == 2
    assert all(p.startswith(b"\x89PNG") for p in pngs)


def _make_underline_form() -> bytes:
    """A flat form with two labelled blanks on ONE line (dense-form case)."""
    from fpdf import FPDF

    pdf = FPDF(unit="pt")
    pdf.add_page(format=(500, 200))
    pdf.set_font("helvetica", "", 12)
    pdf.text(40, 60, "Name: ____________  Mobile No.: ____________")
    return bytes(pdf.output())


def test_extract_line_anchors_blank_run_granularity():
    anchors = pdf_filler.extract_line_anchors(_make_underline_form())
    labels = [a["label"] for a in anchors]
    # Two separate anchors on one line — Name and Mobile No. must not merge.
    assert any("Name" in lbl for lbl in labels)
    assert any("Mobile" in lbl for lbl in labels)
    # The Mobile anchor must sit to the right of the Name anchor (own blank).
    name_a = next(a for a in anchors if "Name" in a["label"])
    mob_a = next(a for a in anchors if "Mobile" in a["label"])
    assert mob_a["x"] > name_a["x"]
    for a in anchors:  # coordinates in-bounds
        assert 0 <= a["x"] <= 500 and 0 <= a["y"] <= 200


def _make_box_form() -> bytes:
    """A flat form with a labelled row of 8 comb boxes (vector rectangles)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((20, 60), "PAN")
    x, y, w = 60, 50, 12
    for _ in range(8):
        page.draw_rect(fitz.Rect(x, y, x + w, y + w))
        x += w
    try:
        return doc.tobytes()
    finally:
        doc.close()


def test_extract_box_rows_detects_comb_grid():
    rows = pdf_filler.extract_box_rows(_make_box_form())
    assert len(rows) == 1
    row = rows[0]
    assert len(row["cells"]) == 8
    assert "PAN" in row["label"]


def test_boxes_to_char_placements_one_char_per_cell():
    rows = pdf_filler.extract_box_rows(_make_box_form())
    placements = pdf_filler.boxes_to_char_placements(rows[0], "abc123")
    assert [p["value"] for p in placements] == ["A", "B", "C", "1", "2", "3"]  # uppercased
    # Each character advances to the next cell (strictly increasing x).
    xs = [p["x"] for p in placements]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)


def test_boxes_space_advances_a_cell():
    rows = pdf_filler.extract_box_rows(_make_box_form())
    placements = pdf_filler.boxes_to_char_placements(rows[0], "A B")
    # 'A' cell0, space skips cell1, 'B' cell2 — so B sits two cells right of A.
    assert [p["value"] for p in placements] == ["A", "B"]
    assert placements[1]["x"] - placements[0]["x"] > 15  # skipped a ~12pt cell


def test_extract_line_anchors_empty_for_no_text():
    # A blank page with no text yields no anchors (→ vision fallback).
    from fpdf import FPDF

    pdf = FPDF(unit="pt")
    pdf.add_page(format=(300, 200))
    assert pdf_filler.extract_line_anchors(bytes(pdf.output())) == []
