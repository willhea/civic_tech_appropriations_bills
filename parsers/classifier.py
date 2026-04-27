"""Format-agnostic line classifier for legislative-bill text.

Both PDF and (future) Word backends share this classifier. Each backend
extracts ``(text, StyleHints)`` from its source and asks the classifier
which structural tag the line carries — ``DIVISION``, ``TITLE``,
``SECTION``, ``APPRO_MAJOR``, ``APPRO_INTERMEDIATE``, ``APPRO_SMALL``,
or ``BODY`` (default).

The classifier is a pure function. Backend-specific layout heuristics
(centering thresholds, column boundaries, font lookups) live in the
backend; the classifier sees only the distilled hints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Tag(str, Enum):
    DIVISION = "division"
    TITLE = "title"
    SECTION = "section"
    APPRO_MAJOR = "appropriations-major"
    APPRO_INTERMEDIATE = "appropriations-intermediate"
    APPRO_SMALL = "appropriations-small"
    BODY = "body"


@dataclass(frozen=True)
class StyleHints:
    """Layout / typography hints distilled from the source format.

    Backends fill in whatever signals they have; absent fields default to
    ``None`` and the classifier falls back to text-only patterns.
    """

    centered: bool | None = None  # line center within ~5% of page width center
    all_caps: bool | None = None  # ratio of upper alpha to total alpha > 0.9
    bold: bool | None = None
    italic: bool | None = None
    indent_level: int | None = None  # 0 = body column, 1 = one tab in, etc.
    font_size: float | None = None
    has_trailing_amount: bool | None = None  # line ends with a $ amount


# DIVISION X — NAME / DIVISION X--NAME / DIVISION X-NAME
_DIVISION_RE = re.compile(
    r"^DIVISION\s+([A-Z]+|\d+)\s*[—\-]+\s*(.+?)\s*$",
)
# TITLE I — NAME (Roman or arabic numerals)
_TITLE_RE = re.compile(
    r"^TITLE\s+([IVXLCDM]+|\d+)\s*[—\-]+\s*(.+?)\s*$",
)
# SEC. 101. or SECTION 101. (optionally followed by header text)
_SECTION_RE = re.compile(
    r"^SEC(?:TION|\.)\s*(\d+[A-Z]?)\.\s*(.*)$",
)
# Run-in header: bold leading clause ending in a period, then content.
# E.g. "SALARIES AND EXPENSES.—For necessary expenses..."
_RUN_IN_RE = re.compile(r"^[A-Z][A-Z0-9 ,&\-/]+\.[\s—\-]")
# Trailing dollar amount: "...$1,234,567,000." or "...$1,234,567."
_TRAILING_AMOUNT_RE = re.compile(r"\$[0-9][0-9,]*(?:\.\d+)?\s*\.?\s*$")


def has_trailing_amount(text: str) -> bool:
    """Return True if ``text`` ends with a dollar amount."""
    return bool(_TRAILING_AMOUNT_RE.search(text.rstrip()))


def is_all_caps(text: str) -> bool:
    """True if alphabetic chars in ``text`` are >=90% uppercase."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.9


def classify(text: str, hints: StyleHints | None = None) -> Tag:
    """Classify a single line / paragraph into a structural tag.

    ``text`` is the line's plain-text content (already cleaned of
    line numbers, page numbers, watermarks, etc.). ``hints`` carries
    layout/typography signals from the source format.
    """
    if hints is None:
        hints = StyleHints()

    stripped = text.strip()
    if not stripped:
        return Tag.BODY

    # DIVISION and TITLE: text pattern is the strong signal; centering
    # and all-caps just reduce false positives if the source supplies them.
    if _DIVISION_RE.match(stripped):
        if hints.centered is False:
            return Tag.BODY
        return Tag.DIVISION
    if _TITLE_RE.match(stripped):
        if hints.centered is False:
            return Tag.BODY
        return Tag.TITLE

    # SEC. N. is unambiguous regardless of layout.
    if _SECTION_RE.match(stripped):
        return Tag.SECTION

    # Appropriations-major: centered all-caps standalone heading that
    # isn't a DIVISION/TITLE/SECTION (those were handled above).
    if hints.centered and (hints.all_caps or is_all_caps(stripped)):
        # Defensive: short single tokens like "DRAFT" leak through if
        # watermark stripping missed them — require at least two words
        # and no trailing amount (which would make this a run-in header).
        if len(stripped.split()) >= 2 and not has_trailing_amount(stripped):
            return Tag.APPRO_MAJOR

    # Appropriations-small: bold run-in header at the start of a paragraph
    # followed by a dollar amount on the same line.
    trailing = hints.has_trailing_amount if hints.has_trailing_amount is not None else has_trailing_amount(stripped)
    if trailing and _RUN_IN_RE.match(stripped):
        return Tag.APPRO_SMALL

    # Appropriations-intermediate: indented all-caps / small-caps heading
    # without a trailing amount. Indent is the strongest available signal.
    if (
        hints.indent_level is not None
        and hints.indent_level >= 1
        and (hints.all_caps or is_all_caps(stripped) or hints.italic)
        and not trailing
        and len(stripped.split()) >= 2
    ):
        return Tag.APPRO_INTERMEDIATE

    return Tag.BODY


def parse_division(text: str) -> tuple[str, str] | None:
    """Return ``(enum, header_text)`` for a DIVISION line, or ``None``."""
    m = _DIVISION_RE.match(text.strip())
    return (m.group(1), m.group(2)) if m else None


def parse_title(text: str) -> tuple[str, str] | None:
    """Return ``(enum, header_text)`` for a TITLE line, or ``None``."""
    m = _TITLE_RE.match(text.strip())
    return (m.group(1), m.group(2)) if m else None


def parse_section(text: str) -> tuple[str, str] | None:
    """Return ``(enum, header_text)`` for a SEC. N. line, or ``None``.

    ``header_text`` may be empty if the section header runs on the next
    line (the caller is responsible for joining wrapped headers before
    classifying).
    """
    m = _SECTION_RE.match(text.strip())
    return (m.group(1), m.group(2).strip()) if m else None


def parse_run_in_header(text: str) -> tuple[str, str] | None:
    """Split a run-in header from its body text.

    "SALARIES AND EXPENSES.—For necessary expenses..." returns
    ``("SALARIES AND EXPENSES", "For necessary expenses...")``.
    Returns ``None`` if the line doesn't have a run-in header.
    """
    stripped = text.strip()
    if not _RUN_IN_RE.match(stripped):
        return None
    # Split on the first period; the run-in header is everything before
    # the period (which the regex already validated as all-caps-ish).
    head, _, rest = stripped.partition(".")
    rest = rest.lstrip(" —-")
    return head.strip(), rest.strip()
