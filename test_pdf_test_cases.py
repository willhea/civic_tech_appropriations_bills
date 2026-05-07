"""Sanity tests for the PDF diff test-case fixture parser.

Verifies that test_data/pdf/118hr8752-changes.md parses cleanly into
PdfTestCase objects. See ~/.claude/plans/let-s-put-together-a-snug-twilight.md.
"""

import pytest

from pdf_test_cases import load_cases

CASES = load_cases()
CASE_IDS = [f"case-{c.number}" for c in CASES]


def test_loads_thirteen_cases():
    assert len(CASES) == 13
    assert [c.number for c in CASES] == list(range(1, 14))


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_change_types_are_valid(case):
    assert case.change_type in {"modified", "added", "removed", "moved"}


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_locations_parse(case):
    for loc in (case.v1_location, case.v2_location):
        if loc is not None:
            assert isinstance(loc, tuple) and len(loc) == 4
            assert all(isinstance(n, int) and n > 0 for n in loc)

    if case.change_type in {"modified", "moved"}:
        assert case.v1_location is not None, f"case {case.number}: v1 must be present"
        assert case.v2_location is not None, f"case {case.number}: v2 must be present"
    elif case.change_type == "added":
        assert case.v1_location is None, f"case {case.number}: v1 should be None for added"
        assert case.v2_location is not None
    elif case.change_type == "removed":
        assert case.v1_location is not None
        assert case.v2_location is None, f"case {case.number}: v2 should be None for removed"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_text_bodies_present(case):
    if case.change_type in {"modified", "moved"}:
        assert case.v1_text.strip(), f"case {case.number}: v1_text should be non-empty"
        assert case.v2_text.strip(), f"case {case.number}: v2_text should be non-empty"
    elif case.change_type == "added":
        assert case.v1_text == "", f"case {case.number}: v1_text should be empty for added"
        assert case.v2_text.strip()
    elif case.change_type == "removed":
        assert case.v1_text.strip()
        assert case.v2_text == "", f"case {case.number}: v2_text should be empty for removed"
