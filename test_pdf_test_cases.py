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
