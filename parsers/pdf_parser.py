"""PDF backend for ``parsers.load_bill_tree``.

Built incrementally across Phase B0-B8. This commit (B0) establishes
the module skeleton and deterministic character extraction; later
phases add line reconstruction, classification, and tree construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bill_tree import BillTree

Char = dict[str, Any]


def _metadata_from_path(pdf_path: Path) -> tuple[int, str, int, str]:
    """Derive ``(congress, bill_type, bill_number, version)`` from path layout.

    Expected layout: ``<corpus>/<congress>-<bill_type>-<bill_number>/<idx>_<slug>.pdf``.
    Components that don't parse fall back to zeros / empty strings rather
    than raising — the caller still gets a usable ``BillTree`` even when
    the file lives outside the corpus convention.
    """
    parent = pdf_path.parent.name
    congress = 0
    bill_type = ""
    bill_number = 0
    parts = parent.split("-")
    if len(parts) >= 3 and parts[0].isdigit() and parts[-1].isdigit():
        try:
            congress = int(parts[0])
            bill_type = "-".join(parts[1:-1])
            bill_number = int(parts[-1])
        except ValueError:
            pass

    version = ""
    stem_parts = pdf_path.stem.split("_", 1)
    if len(stem_parts) == 2:
        version = stem_parts[1]
    return congress, bill_type, bill_number, version


def _sort_chars(chars: list[Char]) -> list[Char]:
    """Sort chars deterministically by ``(round(top, 1), round(x0, 1), text)``.

    Defeats pdfminer.six iteration-order differences so any downstream
    ``synth_id`` / ``match_path`` outputs are byte-for-byte stable
    across runs and platforms.
    """
    return sorted(
        chars,
        key=lambda c: (
            round(c.get("top", 0.0), 1),
            round(c.get("x0", 0.0), 1),
            c.get("text", ""),
        ),
    )


def _extract_pages(pdf_path: Path) -> tuple[list[list[Char]], list[float]]:
    """Read each page's chars and height from ``pdf_path``.

    Each page's chars are sorted via :func:`_sort_chars` before
    return, so the output is deterministic. Returns a tuple of
    ``(pages, heights)`` parallel-indexed.
    """
    import pdfplumber

    pages: list[list[Char]] = []
    heights: list[float] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(_sort_chars(list(page.chars)))
            heights.append(float(page.height))
    return pages, heights


def parse_pdf(pdf_path: Path) -> BillTree:
    """Parse a PDF bill into a ``BillTree``.

    Phase B0 only: extracts and sorts chars deterministically, derives
    bill metadata from the path, and returns an empty tree. Subsequent
    phases populate the nodes:

    - B1: font-size-aware line reconstruction (small-caps reattach)
    - B2: line-number stripping
    - B3: cover-page / preamble guard
    - B4: multi-line TITLE / DIVISION header join
    - B5: body wrap and conservative dehyphenation
    - B6: cross-page continuity
    - B7: walker-compatible structural emission
    - B8: orphan handling
    """
    _pages, _heights = _extract_pages(pdf_path)
    congress, bill_type, bill_number, version = _metadata_from_path(pdf_path)
    return BillTree(congress, bill_type, bill_number, version, [])
