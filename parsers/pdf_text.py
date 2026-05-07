"""PDF text extraction with the smallest set of primitives that fixture cases require.

`Page` is line-aware: every cleaned `Line` carries the source PDF's printed line
number (1-based, the small digit GPO renders in the left margin). Phase 2 uses
those numbers to produce hunk citations like `p.61 L5` and to attach anchor
breadcrumbs by binary-searching the anchor list. The page-level `text` property
is a derived join, so existing consumers (recall test, `page_range_text`) keep
working without change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

_LINE_NUMBER_PREFIX = re.compile(r"^\d{1,2} ", re.MULTILINE)
_NUMBERED_LINE = re.compile(r"^(\d{1,2}) (.*)$")
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
class Line:
    line_number: int | None  # 1-based source PDF line number; None if unnumbered
    text: str  # cleaned line content (line-number prefix stripped)


@dataclass(frozen=True)
class Page:
    page_number: int  # 1-based
    lines: tuple[Line, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


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


def parse_lines(chrome_stripped: str) -> tuple[Line, ...]:
    """Parse chrome-stripped page text into Line records.

    Each body line in a GPO bill begins with `<line_number> <content>`. Lines
    that don't fit (anomalies, empty lines) get `line_number=None`. Soft hyphens
    that span two consecutive lines are rejoined into the earlier line; the
    later line's record is dropped.
    """
    parsed: list[Line] = []
    for raw_line in chrome_stripped.split("\n"):
        m = _NUMBERED_LINE.match(raw_line)
        if m:
            parsed.append(Line(int(m.group(1)), m.group(2)))
        else:
            parsed.append(Line(None, raw_line))

    # Rejoin per-page soft hyphens at line boundaries: when line[i] ends with
    # `WORD-` and line[i+1].text starts with a lowercase letter, merge them.
    merged: list[Line] = []
    i = 0
    while i < len(parsed):
        current = parsed[i]
        if (
            i + 1 < len(parsed)
            and current.text.endswith("-")
            and len(current.text) >= 2
            and current.text[-2].isalnum()
            and parsed[i + 1].text[:1].islower()
        ):
            merged.append(Line(current.line_number, current.text[:-1] + parsed[i + 1].text))
            i += 2
            continue
        merged.append(current)
        i += 1
    return tuple(merged)


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
        pages: list[Page] = []
        for i, page in enumerate(pdf.pages):
            raw = page.extract_text() or ""
            chrome_stripped = strip_page_chrome(raw)
            pages.append(Page(i + 1, parse_lines(chrome_stripped)))
        return pages
