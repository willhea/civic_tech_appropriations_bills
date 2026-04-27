"""Unit tests for parsers.parity_metrics.

Pure-function tests on hand-built BillTrees — no PDFs involved.
"""

from __future__ import annotations

from parsers.parity_metrics import (
    body_similarity_per_match,
    financial_recall,
    match_path_recall,
)

from bill_tree import BillNode, BillTree


def _node(match_path: tuple[str, ...], *, body: str = "", header: str = "") -> BillNode:
    return BillNode(
        match_path=tuple(match_path),
        display_path=tuple(match_path),
        tag="section",
        element_id="x",
        header_text=header,
        body_text=body,
        section_number="",
        division_label="",
    )


def _tree(*nodes: BillNode) -> BillTree:
    return BillTree(118, "hr", 1, "ih", list(nodes))


# --- match_path_recall ----------------------------------------------------


def test_match_path_recall_identical_trees():
    a = _tree(_node(("title-i", "sec-101")), _node(("title-i", "sec-102")))
    b = _tree(_node(("title-i", "sec-101")), _node(("title-i", "sec-102")))
    assert match_path_recall(a, b) == 1.0


def test_match_path_recall_pdf_missing_one_of_two():
    xml = _tree(_node(("a",)), _node(("b",)))
    pdf = _tree(_node(("a",)))
    assert match_path_recall(xml, pdf) == 0.5


def test_match_path_recall_pdf_has_extras_does_not_lower_recall():
    xml = _tree(_node(("a",)))
    pdf = _tree(_node(("a",)), _node(("extra",)))
    assert match_path_recall(xml, pdf) == 1.0


def test_match_path_recall_empty_xml_is_vacuously_one():
    """Empty XML is a degenerate case; callers should sanity-check the XML
    has nodes separately before trusting the metric."""
    xml = _tree()
    pdf = _tree(_node(("a",)))
    assert match_path_recall(xml, pdf) == 1.0


def test_match_path_recall_empty_pdf_is_zero_when_xml_has_nodes():
    xml = _tree(_node(("a",)), _node(("b",)))
    pdf = _tree()
    assert match_path_recall(xml, pdf) == 0.0


# --- body_similarity_per_match -------------------------------------------


def test_body_similarity_returns_one_for_identical_text():
    xml = _tree(_node(("a",), body="hello world"))
    pdf = _tree(_node(("a",), body="hello world"))
    sims = body_similarity_per_match(xml, pdf)
    assert sims[("a",)] == 1.0


def test_body_similarity_normalizes_whitespace():
    xml = _tree(_node(("a",), body="hello   world\n  again"))
    pdf = _tree(_node(("a",), body="hello world again"))
    sims = body_similarity_per_match(xml, pdf)
    assert sims[("a",)] == 1.0


def test_body_similarity_partial_overlap_strictly_between_zero_and_one():
    xml = _tree(_node(("a",), body="The quick brown fox jumps"))
    pdf = _tree(_node(("a",), body="The quick red fox jumps"))
    sims = body_similarity_per_match(xml, pdf)
    assert 0.0 < sims[("a",)] < 1.0


def test_body_similarity_only_matched_paths_in_result():
    xml = _tree(_node(("a",), body="x"), _node(("b",), body="y"))
    pdf = _tree(_node(("a",), body="x"))
    sims = body_similarity_per_match(xml, pdf)
    assert ("a",) in sims
    assert ("b",) not in sims


# --- financial_recall ----------------------------------------------------


def test_financial_recall_identical_amounts_returns_one():
    xml = _tree(_node(("a",), body="appropriated $1,500,000 and $750,000"))
    pdf = _tree(_node(("a",), body="appropriated $1,500,000 and $750,000"))
    assert financial_recall(xml, pdf) == 1.0


def test_financial_recall_missing_one_amount_in_pdf():
    xml = _tree(_node(("a",), body="$1,000 plus $2,000"))
    pdf = _tree(_node(("a",), body="$1,000"))
    assert financial_recall(xml, pdf) == 0.5


def test_financial_recall_multiset_semantics():
    """Repeated amounts count: $100 twice in XML, once in PDF -> 2/3."""
    xml = _tree(_node(("a",), body="$100 and $100 and $200"))
    pdf = _tree(_node(("a",), body="$100 and $200"))
    assert financial_recall(xml, pdf) == 2 / 3


def test_financial_recall_excludes_nodes_with_no_xml_amounts():
    xml = _tree(
        _node(("a",), body="$1,000"),
        _node(("b",), body="no amounts here"),
    )
    pdf = _tree(
        _node(("a",), body="$1,000"),
        _node(("b",), body="still no amounts"),
    )
    assert financial_recall(xml, pdf) == 1.0


def test_financial_recall_no_amounts_anywhere_is_vacuously_one():
    xml = _tree(_node(("a",), body="text without dollars"))
    pdf = _tree(_node(("a",), body="text without dollars"))
    assert financial_recall(xml, pdf) == 1.0


def test_financial_recall_pdf_missing_node_treats_amounts_as_unrecovered():
    xml = _tree(_node(("a",), body="$100 $200"))
    pdf = _tree()
    assert financial_recall(xml, pdf) == 0.0


def test_financial_recall_averages_across_nodes_with_amounts():
    xml = _tree(
        _node(("a",), body="$100 $200"),  # PDF recovers 1/2
        _node(("b",), body="$50"),  # PDF recovers 1/1
    )
    pdf = _tree(
        _node(("a",), body="$100"),
        _node(("b",), body="$50"),
    )
    # mean(0.5, 1.0) = 0.75
    assert financial_recall(xml, pdf) == 0.75
