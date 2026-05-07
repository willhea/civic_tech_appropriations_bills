"""Anchor extraction for PDF bills.

An Anchor is a landmark label (TITLE / SEC. / account heading) the GPO PDF
carries reliably. The diff layer attaches the nearest preceding anchor to each
hunk as a "where am I" breadcrumb. When no anchor resolves cleanly, the diff
falls back to the page/line citation alone — anchors degrade, they don't gate.

Operates on `parsers.pdf_text.Page` objects, which carry per-line source PDF
line numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from parsers.pdf_text import Page, parse_lines, strip_page_chrome

AnchorKind = Literal["title", "section", "account"]


@dataclass(frozen=True)
class Anchor:
    page_number: int  # 1-based
    line_number: int  # 1-based, from the source PDF's printed line numbers
    kind: AnchorKind
    text: str  # canonical form, e.g. "TITLE I", "SEC. 406", "OPERATIONS AND SUPPORT"


_TITLE_PATTERN = re.compile(r"^TITLE\s+([IVXLC]+)\b.*$")
_SECTION_PATTERN = re.compile(r"^(SEC(?:TION)?\.?\s+\d+)\b")
_FOR_NECESSARY_EXPENSES = re.compile(r"^For necessary expenses of\b", re.IGNORECASE)


def _is_uppercase_heading(content: str) -> bool:
    """Heuristic: line is mostly uppercase letters, not a TITLE/SEC. heading.

    Allows commas, parentheses, ampersands, periods. Rejects lines with any
    lowercase ASCII letters.
    """
    if not content.strip():
        return False
    if _TITLE_PATTERN.match(content) or _SECTION_PATTERN.match(content):
        return False
    has_letter = False
    for ch in content:
        if ch.isalpha():
            has_letter = True
            if ch.islower():
                return False
    return has_letter


def _scan_anchors_in_page(page_number: int, raw_text: str) -> list[Anchor]:
    """Scan one page's raw chrome-stripped, line-numbered text for anchors.

    Test-only entry point that takes a raw `<n> content` string per line.
    Production path uses `extract_anchors(pages)` which reads `Page.lines`.
    """

    page = Page(page_number, parse_lines(strip_page_chrome(raw_text)))
    return _anchors_from_page(page)


def _anchors_from_page(page: Page) -> list[Anchor]:
    """Scan a Page's lines for anchors, returning them in line order.

    Account headings are detected by walking backward from each `For necessary
    expenses of` trigger up to 3 lines and taking the nearest uppercase
    heading.
    """
    anchors: list[Anchor] = []
    for idx, line in enumerate(page.lines):
        if line.line_number is None:
            continue
        title_match = _TITLE_PATTERN.match(line.text)
        if title_match:
            anchors.append(Anchor(page.page_number, line.line_number, "title", f"TITLE {title_match.group(1)}"))
            continue
        section_match = _SECTION_PATTERN.match(line.text)
        if section_match:
            canonical = re.sub(r"\s+", " ", section_match.group(1))
            anchors.append(Anchor(page.page_number, line.line_number, "section", canonical))
            continue
        if _FOR_NECESSARY_EXPENSES.match(line.text):
            for back in range(idx - 1, max(idx - 4, -1), -1):
                back_line = page.lines[back]
                if back_line.line_number is None:
                    continue
                if _is_uppercase_heading(back_line.text):
                    candidate = Anchor(page.page_number, back_line.line_number, "account", back_line.text.strip())
                    if candidate not in anchors:
                        anchors.append(candidate)
                    break

    anchors.sort(key=lambda a: a.line_number)
    return anchors


def extract_anchors(pages: list[Page]) -> list[Anchor]:
    """Extract all anchors from a list of cleaned Pages, in document order."""
    all_anchors: list[Anchor] = []
    for page in pages:
        all_anchors.extend(_anchors_from_page(page))
    return all_anchors


def breadcrumb_for(anchor: Anchor, all_anchors: tuple[Anchor, ...] | list[Anchor]) -> tuple[str, ...]:
    """Walk back through `all_anchors` from `anchor` to assemble a parent chain.

    For a TITLE anchor: returns just `("TITLE I",)`.
    For a SECTION anchor: returns `("TITLE IV", "SEC. 406")` if a preceding
    TITLE exists, else just `("SEC. 406",)`.
    For an ACCOUNT anchor: returns `("TITLE I", "OPERATIONS AND SUPPORT")` if
    a preceding TITLE exists, else just `("OPERATIONS AND SUPPORT",)`.

    The agency-level heading (e.g. "OFFICE OF THE SECRETARY") is not currently
    captured by anchor extraction; once that lands the chain becomes three
    levels deep without changing this function's contract.
    """
    if anchor.kind == "title":
        return (anchor.text,)
    # Find anchor's index by identity
    try:
        idx = list(all_anchors).index(anchor)
    except ValueError:
        return (anchor.text,)
    # Walk back for the most recent preceding TITLE
    for j in range(idx - 1, -1, -1):
        if all_anchors[j].kind == "title":
            return (all_anchors[j].text, anchor.text)
    return (anchor.text,)
