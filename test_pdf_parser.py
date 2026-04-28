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


def test_extract_pages_is_deterministic_across_calls():
    """Two calls to ``_extract_pages`` on the same PDF return equal output.

    Sorting raw chars by ``(round(top, 1), round(x0, 1), text)`` defeats
    pdfminer.six iteration-order differences so synthetic IDs and
    match_paths produced by later phases are stable. As B1+ adds nodes,
    this determinism propagates up into the ``BillTree``.
    """
    from parsers.pdf_parser import _extract_pages

    pages_a, heights_a = _extract_pages(FIXTURE)
    pages_b, heights_b = _extract_pages(FIXTURE)
    assert heights_a == heights_b
    assert pages_a == pages_b


def test_metadata_from_path_parses_corpus_layout():
    """``bills/<congress>-<type>-<number>/<idx>_<slug>.pdf`` decomposes
    into the expected metadata tuple."""
    from pathlib import Path

    from parsers.pdf_parser import _metadata_from_path

    p = Path("bills/118-hr-8752/1_reported-in-house.pdf")
    assert _metadata_from_path(p) == (118, "hr", 8752, "reported-in-house")


def test_metadata_from_path_returns_empty_for_unrecognized_layout():
    from pathlib import Path

    from parsers.pdf_parser import _metadata_from_path

    p = Path("/tmp/some-arbitrary.pdf")
    assert _metadata_from_path(p) == (0, "", 0, "")
