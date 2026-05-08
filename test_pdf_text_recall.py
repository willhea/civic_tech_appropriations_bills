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


def _normalize(text: str) -> str:
    return _WS.sub(" ", normalize_glyphs(text)).strip()


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
