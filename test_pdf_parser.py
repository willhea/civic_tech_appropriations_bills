"""Tests for the PDF backend of ``parsers.load_bill_tree``.

The smoke test below uses a committed single-page fixture and is
EXPECTED RED until Phase B1 lands a working extractor and registers
it with the parsers dispatcher. After B1 lands the test flips green
and stays green for the rest of the rebuild.

Phase B0-B8 will add more tests here as each extraction capability
lands.
"""

from __future__ import annotations

from pathlib import Path

from parsers import load_bill_tree

FIXTURE = Path(__file__).parent / "test_data" / "pdf" / "118hr8752-page5.pdf"


def test_committed_fixture_yields_at_least_one_bill_node():
    """Single-page GPO PDF must produce at least one ``BillNode``.

    The fixture is page 5 of ``bills/118-hr-8752/1_reported-in-house.pdf``
    — contains real section content (``SEC. 102.`` and following body
    text) so a working parser should recover at least one node.
    """
    assert FIXTURE.exists(), f"Committed fixture missing: {FIXTURE}"
    tree = load_bill_tree(FIXTURE)
    assert len(tree.nodes) > 0
