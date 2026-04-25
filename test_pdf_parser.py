"""Tests for the PDF parser primitives.

Uses synthetic pdfplumber-shaped char dicts so we don't need a real PDF
on disk. The shape mirrors what ``pdfplumber.Page.chars`` returns:
``{text, x0, x1, top, bottom, size, fontname, matrix, non_stroking_color}``.
"""

from __future__ import annotations

import math

import pytest

from parsers import pdf_parser as pp

# --- Helpers --------------------------------------------------------------


def _char(
    text: str,
    x0: float,
    top: float,
    *,
    size: float = 11.0,
    fontname: str = "Times-Roman",
    rotation: float = 0.0,
    color=0.0,
) -> dict:
    rad = math.radians(rotation)
    a = size * math.cos(rad)
    b = size * math.sin(rad)
    c = -size * math.sin(rad)
    d = size * math.cos(rad)
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + size * 0.5,
        "top": top,
        "bottom": top + size,
        "size": size,
        "fontname": fontname,
        "matrix": (a, b, c, d, 0.0, 0.0),
        "non_stroking_color": color,
    }


def _line_at(text: str, x0: float, top: float, **kwargs) -> list[dict]:
    """A horizontal run of body chars laying out ``text`` left to right."""
    chars = []
    cursor = x0
    for ch in text:
        chars.append(_char(ch, cursor, top, **kwargs))
        cursor += kwargs.get("size", 11.0) * 0.5
    return chars


# --- Watermark stripping (char-level) -------------------------------------


def test_strip_rotated_watermark_chars():
    body = _line_at("Hello world", 100, 200)
    watermark = _line_at("DRAFT", 250, 400, rotation=45.0)
    out = pp.strip_watermark_chars(body + watermark)
    text = "".join(c["text"] for c in out)
    assert "Hello world" in text
    assert "DRAFT" not in text


def test_strip_pale_grey_watermark_chars():
    body = _line_at("Hello world", 100, 200)
    watermark = _line_at("CONFIDENTIAL", 200, 400, color=(0.85, 0.85, 0.85))
    out = pp.strip_watermark_chars(body + watermark)
    text = "".join(c["text"] for c in out)
    assert "CONFIDENTIAL" not in text
    assert "Hello world" in text


def test_body_with_literal_word_draft_survives():
    """A horizontal black 'DRAFT' in body text is NOT a watermark."""
    body = _line_at("Discussion of DRAFT regulations.", 100, 200)
    out = pp.strip_watermark_chars(body)
    text = "".join(c["text"] for c in out)
    assert "DRAFT" in text


# --- Line grouping --------------------------------------------------------


def test_group_lines_buckets_chars_by_top():
    chars = _line_at("Line one", 100, 100) + _line_at("Line two", 100, 130)
    lines = pp.group_lines(chars)
    assert [ln["text"] for ln in lines] == ["Line one", "Line two"]


def test_group_lines_tolerates_minor_top_drift():
    # Chars within ±2px should be one line.
    a = _line_at("A B C", 100, 100)
    a[1]["top"] = 101.0  # mild drift — same visual line.
    a[2]["top"] = 99.5
    lines = pp.group_lines(a)
    assert len(lines) == 1
    assert lines[0]["text"] == "ABC".replace("ABC", "A B C")  # preserved order


# --- Page noise stripping -------------------------------------------------


def test_strip_line_numbers_in_left_margin():
    chars = _line_at("3", 60, 100, size=9.0) + _line_at("Body text here", 110, 100)
    lines = pp.group_lines(chars)
    cleaned = pp.strip_page_noise(lines, page_height=792)
    assert all("3" not in ln["text"][:1] for ln in cleaned)
    assert any("Body text here" in ln["text"] for ln in cleaned)


def test_strip_page_numbers_at_bottom():
    chars = _line_at("Body", 110, 100) + _line_at("42", 300, 760, size=9.0)
    lines = pp.group_lines(chars)
    cleaned = pp.strip_page_noise(lines, page_height=792)
    assert any("Body" in ln["text"] for ln in cleaned)
    assert not any(ln["text"].strip() == "42" for ln in cleaned)


# --- Cross-page running header / overlay ---------------------------------


def test_strip_running_header_when_repeated_across_pages():
    pages = []
    for _ in range(8):
        chars = _line_at("H. R. 1234", 200, 20) + _line_at("Body content", 110, 200)
        pages.append(pp.group_lines(chars))
    cleaned = pp._strip_running_headers(pages)
    for page in cleaned:
        assert all("H. R." not in ln["text"] for ln in page)


def test_strip_repeated_centered_overlay():
    """A short centered text repeated on every page is treated as a watermark."""
    pages = []
    for _ in range(6):
        chars = _line_at("PRE-DECISIONAL", 250, 400, size=14.0) + _line_at("Some body text", 110, 200)
        pages.append(pp.group_lines(chars))
    cleaned = pp._strip_repeated_overlay(pages, page_height=792)
    for page in cleaned:
        assert all("PRE-DECISIONAL" not in ln["text"] for ln in page)


def test_overlay_stripping_keeps_unique_short_lines():
    """One-off short lines (e.g., page-specific labels) must survive."""
    pages = []
    for i in range(4):
        chars = _line_at(f"Unique {i}", 250, 400, size=14.0) + _line_at("Body", 110, 200)
        pages.append(pp.group_lines(chars))
    cleaned = pp._strip_repeated_overlay(pages, page_height=792)
    found = [ln["text"] for page in cleaned for ln in page if "Unique" in ln["text"]]
    assert len(found) == 4


# --- Wrapped header join --------------------------------------------------


def test_join_wrapped_headers_concatenates_short_continuation():
    line1 = {
        "text": "DEPARTMENT OF DEFENSE",
        "top": 100,
        "x0": 200.0,
        "x1": 400.0,
        "chars": [],
    }
    line2 = {
        "text": "APPROPRIATIONS",
        "top": 116,
        "x0": 200.0,
        "x1": 350.0,
        "chars": [],
    }
    out = pp.join_wrapped_headers([line1, line2])
    assert len(out) == 1
    assert out[0]["text"] == "DEPARTMENT OF DEFENSE APPROPRIATIONS"


def test_join_wrapped_headers_does_not_join_terminated_line():
    line1 = {
        "text": "Body sentence ending in period.",
        "top": 100,
        "x0": 110.0,
        "x1": 300.0,
        "chars": [],
    }
    line2 = {
        "text": "Next paragraph",
        "top": 116,
        "x0": 110.0,
        "x1": 200.0,
        "chars": [],
    }
    out = pp.join_wrapped_headers([line1, line2])
    assert len(out) == 2


# --- End-to-end: synthetic pages -> BillTree ------------------------------


def _centered_line(text: str, top: float, page_width: float = 612.0, size: float = 11.0):
    text_width = size * 0.5 * len(text)
    x0 = (page_width - text_width) / 2
    return _line_at(text, x0, top, size=size)


def test_parse_pdf_pages_builds_section_tree():
    page_chars = (
        _centered_line("DIVISION A—DEFENSE APPROPRIATIONS", 60)
        + _centered_line("TITLE I—MILITARY PERSONNEL", 90)
        + _line_at("SEC. 101. SHORT TITLE.", 110, 130)
        + _line_at(
            "This Act may be cited as the Defense Appropriations Act.",
            110,
            150,
        )
    )
    tree = pp.parse_pdf_pages(
        [page_chars],
        [792.0],
        congress=118,
        bill_type="hr",
        bill_number=4366,
        version="reported-in-house",
    )
    assert tree.congress == 118
    assert tree.bill_type == "hr"
    assert tree.bill_number == 4366
    paths = [n.match_path for n in tree.nodes]
    # Section path should reflect title + section enum.
    assert any("sec. 101" in "/".join(p) for p in paths), paths


def test_parse_pdf_pages_drops_watermark_text_from_body():
    """A diagonal 'DRAFT' watermark must not appear in the resulting body text."""
    body = _line_at("This is the body of section 1.", 110, 200)
    watermark = _line_at("DRAFT", 250, 400, rotation=45.0)
    page_chars = _line_at("SEC. 1. INTRODUCTION.", 110, 130) + body + watermark
    tree = pp.parse_pdf_pages(
        [page_chars],
        [792.0],
        congress=118,
        bill_type="hr",
        bill_number=1,
        version="v",
    )
    body_text = " ".join(n.body_text for n in tree.nodes)
    assert "DRAFT" not in body_text
    assert "body of section 1" in body_text


# --- Color luminance edge cases ------------------------------------------


@pytest.mark.parametrize(
    "color,expected",
    [
        (None, 0.0),
        (0.0, 0.0),
        (1.0, 1.0),
        ((0.85, 0.85, 0.85), pytest.approx(0.85, abs=0.01)),
        ([0.5], 0.5),
    ],
)
def test_color_luminance(color, expected):
    assert pp._color_luminance(color) == expected


# --- Dispatcher behavior --------------------------------------------------


def test_load_bill_tree_rejects_docx(tmp_path):
    from parsers import UnsupportedFormatError, load_bill_tree

    fake = tmp_path / "bill.docx"
    fake.write_bytes(b"")
    with pytest.raises(UnsupportedFormatError):
        load_bill_tree(fake)


def test_load_bill_tree_rejects_unknown_extension(tmp_path):
    from parsers import UnsupportedFormatError, load_bill_tree

    fake = tmp_path / "bill.txt"
    fake.write_text("not a real bill")
    with pytest.raises(UnsupportedFormatError):
        load_bill_tree(fake)
