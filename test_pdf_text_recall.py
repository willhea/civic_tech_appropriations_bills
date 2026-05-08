"""End-to-end recall: does naïve pdfplumber extraction contain each fixture's expected text?

Per `plans/pdf-text-diff-fixture-first.md`, this is the spec. Step 1 records the
N/M pass count as the baseline; Step 3 drives that count up by adding the smallest
primitives that earn their keep.

Comparison is whitespace-normalized substring match — permissive on purpose, since
the goal is recall, not byte-exact reproduction.
"""

from __future__ import annotations

import re

import pytest

from parsers.pdf_text import normalize_glyphs, page_range_text
from pdf_test_cases import PdfTestCase, load_cases

_WS = re.compile(r"\s+")
# Real compounds like `Child-Rescue` that wrap at a line boundary surface as
# `Child- Rescue` after extraction. The `parse_lines` lowercase guard preserves
# the hyphen but can't tell a soft wrap from a compound at the wrap point, so a
# space leaks in. Positional disambiguation was attempted (see git history) but
# couldn't reliably distinguish all-caps soft hyphens from compounds. Collapse
# the artifact at compare-time only — the diff layer is unaffected.
_WRAPPED_COMPOUND = re.compile(r"(\w)- (\w)")


def _normalize(text: str) -> str:
    canonical = _WS.sub(" ", normalize_glyphs(text)).strip()
    return _WRAPPED_COMPOUND.sub(r"\1-\2", canonical)


def _legs():
    cases = load_cases()
    legs = []
    for case in cases:
        for version in ("v1", "v2"):
            location = case.v1_location if version == "v1" else case.v2_location
            text = case.v1_text if version == "v1" else case.v2_text
            if location is None or not text:
                continue
            legs.append(pytest.param(case, version, id=f"case{case.number}-{version}"))
    return legs


@pytest.mark.parametrize("case,version", _legs())
def test_recall(case: PdfTestCase, version: str, hr8752_v1_pages, hr8752_v2_pages):
    pages = hr8752_v1_pages if version == "v1" else hr8752_v2_pages
    location = case.v1_location if version == "v1" else case.v2_location
    expected = case.v1_text if version == "v1" else case.v2_text
    assert location is not None

    start_page, _, end_page, _ = location
    extracted = _normalize(page_range_text(pages, start_page, end_page))
    expected_norm = _normalize(expected)

    assert expected_norm in extracted, (
        f"Case {case.number} {version}: expected text not found in extracted page range p.{start_page}-p.{end_page}"
    )
