"""PDF text extraction with the smallest set of primitives that fixture cases require."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

_LINE_NUMBER_PREFIX = re.compile(r"^\d{1,2} ", re.MULTILINE)
_SOFT_HYPHEN_BREAK = re.compile(r"(\w)-\n([a-z])")
_PAGE_HEADER_NUMBER = re.compile(r"\A\d+\n")
_PAGE_FOOTER_AND_BELOW = re.compile(r"\n?•HR\b.*\Z", re.DOTALL)
_SMART_GLYPHS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
    }
)


@dataclass(frozen=True)
class Page:
    page_number: int  # 1-based
    text: str


def strip_line_numbers(text: str) -> str:
    """Remove leading 1- or 2-digit line numbers (followed by a space) from each line."""
    return _LINE_NUMBER_PREFIX.sub("", text)


def strip_page_chrome(text: str) -> str:
    """Remove top-of-page number and bottom-of-page chrome (•HR, VerDate, watermark).

    The `•HR` footer marker is always followed by VerDate and any reversed-glyph
    watermark, so dropping everything from `•HR` to end-of-text covers all three.
    """
    text = _PAGE_HEADER_NUMBER.sub("", text)
    text = _PAGE_FOOTER_AND_BELOW.sub("", text)
    return text


def rejoin_soft_hyphens(text: str) -> str:
    """Join `WORD-\\nword` (lowercase continuation) into `WORDword`.

    GPO bills break long words at syllable boundaries with `-\\n` followed by a
    lowercase letter. Real compounds like `Child-Rescue` keep an uppercase
    continuation, so the lowercase guard preserves them.
    """
    return _SOFT_HYPHEN_BREAK.sub(r"\1\2", text)


def normalize_glyphs(text: str) -> str:
    """Map typographic glyphs to ASCII equivalents for comparison-time use.

    Em/en-dashes become ` - ` (space-padded so whitespace normalization handles
    spaced and unspaced source forms). Smart single/double quotes become their
    ASCII counterparts. GPO encodes double quotes as two adjacent single-glyph
    smart quotes (`‘‘…’’`), so paired ASCII apostrophes collapse to `"`.

    The extractor itself preserves original glyphs; this helper exists so
    comparison and diff layers can canonicalize without losing source bytes.
    """
    text = text.replace("—", " - ").replace("–", " - ")
    text = text.translate(_SMART_GLYPHS)
    text = text.replace("''", '"')
    return text


def page_range_text(pages: list[Page], start_page: int, end_page: int) -> str:
    """Concatenate page texts in [start_page, end_page] and rejoin cross-page soft hyphens.

    Per-page cleanup handles intra-page hyphens. Cross-page hyphens (where one
    page ends with `word-` and the next begins with the continuation) only
    surface after concatenation, so the rejoin pass runs again on the seam.
    """
    joined = "\n".join(p.text for p in pages if start_page <= p.page_number <= end_page)
    return rejoin_soft_hyphens(joined)


def extract_clean_pages(pdf_path: Path) -> list[Page]:
    with pdfplumber.open(pdf_path) as pdf:
        return [
            Page(i + 1, rejoin_soft_hyphens(strip_line_numbers(strip_page_chrome(page.extract_text() or ""))))
            for i, page in enumerate(pdf.pages)
        ]
