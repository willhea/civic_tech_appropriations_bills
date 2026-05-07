"""Sanity tests for the PDF diff test-case fixture parser.

Verifies that test_data/pdf/118hr8752-changes.md parses cleanly into
PdfTestCase objects. See ~/.claude/plans/let-s-put-together-a-snug-twilight.md.
"""

from pdf_test_cases import load_cases


def test_loads_thirteen_cases():
    cases = load_cases()
    assert len(cases) == 13
    assert [c.number for c in cases] == list(range(1, 14))
