"""Recall test for diff_pdf against the 13-case spec in test_data/pdf/118hr8752-changes.md.

Each fixture case asserts:
  1. A hunk exists whose page+line range covers the case's location(s).
  2. The hunk's change_type matches the fixture's declared type.
  3. For numeric cases (cases 1-8: floor amendment annotations), the hunk
     has has_amendment_annotations=True.

The fixture is the spec; failures here are the things the diff doesn't
yet surface correctly. Document gaps in plans/pdf-text-diff-findings.md
with one-line rationale before declaring done.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from diff_pdf import PdfDiff, PdfHunk, diff_pdfs
from parsers.pdf_text import extract_clean_pages
from pdf_test_cases import PdfTestCase, load_cases

BILLS_DIR = Path(__file__).parent / "bills"
HR8752_V1 = BILLS_DIR / "118-hr-8752" / "1_reported-in-house.pdf"
HR8752_V2 = BILLS_DIR / "118-hr-8752" / "2_engrossed-in-house.pdf"


@pytest.fixture(scope="module")
def hr8752_pdf_diff() -> PdfDiff:
    if not HR8752_V1.exists() or not HR8752_V2.exists():
        pytest.skip("HR 8752 PDFs not present")
    v1 = extract_clean_pages(HR8752_V1)
    v2 = extract_clean_pages(HR8752_V2)
    return diff_pdfs(v1, v2)


def _location_within_range(
    hunk_range: tuple[int, int, int, int] | None,
    location: tuple[int, int, int, int] | None,
) -> bool:
    """True if `location`'s start falls within `hunk_range`'s [start, end]."""
    if hunk_range is None or location is None:
        return hunk_range is None and location is None
    sp, sl, ep, el = hunk_range
    csp, csl, _, _ = location
    # Treat unnumbered (-1) as 0 for start, "very large" for end so it's permissive.
    hunk_start = (sp, sl if sl >= 0 else 0)
    hunk_end = (ep, el if el >= 0 else 10_000)
    return hunk_start <= (csp, csl) <= hunk_end


def _hunk_covering(diff: PdfDiff, case: PdfTestCase) -> PdfHunk | None:
    """Find the hunk whose v1/v2 ranges cover the case's v1/v2 locations.

    A hunk matches a case when each side's "has a range?" lines up with the
    case's "has a location?" — i.e. an added case (v1_location=None) only
    matches an added hunk (v1_range=None), and so on. The location-covers
    check then confirms the present sides line up positionally.
    """
    for h in diff.hunks:
        if (case.v1_location is not None) != (h.v1_range is not None):
            continue
        if (case.v2_location is not None) != (h.v2_range is not None):
            continue
        v1_ok = case.v1_location is None or _location_within_range(h.v1_range, case.v1_location)
        v2_ok = case.v2_location is None or _location_within_range(h.v2_range, case.v2_location)
        if v1_ok and v2_ok:
            return h
    return None


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: f"case{c.number}")
class TestRecall:
    def test_hunk_exists_for_case(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        h = _hunk_covering(hr8752_pdf_diff, case)
        assert h is not None, f"Case {case.number}: no hunk covers v1={case.v1_location} v2={case.v2_location}"

    def test_change_type_matches(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        h = _hunk_covering(hr8752_pdf_diff, case)
        assert h is not None
        assert h.change_type == case.change_type, (
            f"Case {case.number} ({case.title}): expected change_type={case.change_type!r}, got {h.change_type!r}"
        )

    def test_amendment_annotation_flag_for_numeric_cases(self, case: PdfTestCase, hr8752_pdf_diff: PdfDiff):
        # Cases 1-8 in the fixture are floor amendment additions; the hunk
        # should carry has_amendment_annotations=True. Other cases either
        # have no amendments (9, 10, 11, 13) or have them in long bodies
        # (12) where we still expect the flag.
        if "annotation" not in case.expected_what_changed.lower() and case.expected_net is None:
            pytest.skip("not a financial annotation case")
        h = _hunk_covering(hr8752_pdf_diff, case)
        assert h is not None
        assert h.has_amendment_annotations, (
            f"Case {case.number} ({case.title}): expected has_amendment_annotations=True"
        )
