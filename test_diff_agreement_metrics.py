"""Unit tests for parsers.diff_agreement_metrics.

Pure-function tests on hand-built ``BillDiff`` objects -- no real bill
parsing involved.
"""

from __future__ import annotations

import math
from collections import Counter

from diff_bill import BillDiff, NodeDiff
from parsers.diff_agreement_metrics import (
    change_type_jaccard,
    financial_total_agreement,
    modified_section_overlap,
    summary_count_delta,
    unpair_rate,
)


def _node(
    match_path: tuple[str, ...],
    change_type: str,
    *,
    old_text: str | None = None,
    new_text: str | None = None,
    section_number: str = "",
) -> NodeDiff:
    return NodeDiff(
        display_path_old=tuple(match_path) if old_text is not None else None,
        display_path_new=tuple(match_path) if new_text is not None else None,
        match_path=tuple(match_path),
        change_type=change_type,
        old_text=old_text,
        new_text=new_text,
        text_diff=None,
        section_number=section_number,
        element_id_old="x",
        element_id_new="x",
    )


def _diff(*nodes: NodeDiff) -> BillDiff:
    return BillDiff(
        old_version="rh",
        new_version="eh",
        congress=118,
        bill_type="hr",
        bill_number=1,
        summary=dict(Counter(n.change_type for n in nodes)),
        changes=list(nodes),
    )


# --- summary_count_delta -----------------------------------------------


def test_summary_count_delta_identical_summaries_is_zero_per_type():
    xml = _diff(_node(("a",), "modified"), _node(("b",), "modified"), _node(("c",), "added"))
    pdf = _diff(_node(("x",), "modified"), _node(("y",), "modified"), _node(("z",), "added"))
    out = summary_count_delta(xml, pdf)
    assert out == {"added": 0.0, "removed": 0.0, "modified": 0.0}


def test_summary_count_delta_off_by_one_modified_normalized_by_xml_count():
    xml = _diff(*[_node((str(i),), "modified") for i in range(10)])
    pdf = _diff(*[_node((str(i),), "modified") for i in range(11)])
    out = summary_count_delta(xml, pdf)
    assert out["modified"] == 0.1
    assert out["added"] == 0.0
    assert out["removed"] == 0.0


def test_summary_count_delta_both_zero_is_zero_not_division_by_zero():
    xml = _diff(_node(("a",), "unchanged"))
    pdf = _diff(_node(("b",), "unchanged"))
    out = summary_count_delta(xml, pdf)
    assert out == {"added": 0.0, "removed": 0.0, "modified": 0.0}


def test_summary_count_delta_xml_zero_pdf_nonzero_uses_max1_denominator():
    """When XML has zero of a type but PDF has some, we still want a
    finite delta. Convention: divide by max(xml, 1) so the metric
    reflects "how many spurious"."""
    xml = _diff(_node(("a",), "modified"))
    pdf = _diff(_node(("a",), "modified"), _node(("b",), "added"), _node(("c",), "added"))
    out = summary_count_delta(xml, pdf)
    assert out["added"] == 2.0


# --- financial_total_agreement -----------------------------------------


def test_financial_total_agreement_identical_amounts_is_zero_error():
    xml = _diff(_node(("a",), "modified", old_text="was $1,000,000", new_text="is $1,500,000"))
    pdf = _diff(_node(("a",), "modified", old_text="was $1,000,000", new_text="is $1,500,000"))
    out = financial_total_agreement(xml, pdf)
    assert out["old_abs_pct_error"] == 0.0
    assert out["new_abs_pct_error"] == 0.0
    assert out["xml_old_total"] == 1_000_000
    assert out["xml_new_total"] == 1_500_000


def test_financial_total_agreement_pdf_recovers_half_yields_05_error():
    xml = _diff(
        _node(("a",), "modified", old_text="was $1,000,000", new_text="is $2,000,000"),
        _node(("b",), "modified", old_text="was $1,000,000", new_text="is $2,000,000"),
    )
    pdf = _diff(
        _node(("a",), "modified", old_text="was $1,000,000", new_text="is $2,000,000"),
    )
    out = financial_total_agreement(xml, pdf)
    assert out["old_ratio"] == 0.5
    assert out["new_ratio"] == 0.5
    assert out["old_abs_pct_error"] == 0.5
    assert out["new_abs_pct_error"] == 0.5


def test_financial_total_agreement_both_empty_is_zero_error_not_divide_by_zero():
    xml = _diff(_node(("a",), "modified", old_text="text without dollars", new_text="more text"))
    pdf = _diff(_node(("a",), "modified", old_text="text without dollars", new_text="more text"))
    out = financial_total_agreement(xml, pdf)
    assert out["old_abs_pct_error"] == 0.0
    assert out["new_abs_pct_error"] == 0.0
    assert out["xml_old_total"] == 0
    assert out["pdf_old_total"] == 0


def test_financial_total_agreement_xml_zero_pdf_nonzero_returns_inf():
    """Spurious dollars in PDF that XML doesn't see -> inf error.
    Caller's threshold check fails naturally."""
    xml = _diff(_node(("a",), "modified", old_text="text", new_text="text"))
    pdf = _diff(_node(("a",), "modified", old_text="$500", new_text="$1,000"))
    out = financial_total_agreement(xml, pdf)
    assert out["old_abs_pct_error"] == math.inf
    assert out["new_abs_pct_error"] == math.inf


def test_financial_total_agreement_skips_non_financial_nodes():
    """compute_financial_change returns None for sections with no
    amounts; those don't contribute to the totals."""
    xml = _diff(
        _node(("a",), "modified", old_text="$100", new_text="$200"),
        _node(("b",), "modified", old_text="just words", new_text="more words"),
    )
    pdf = _diff(
        _node(("a",), "modified", old_text="$100", new_text="$200"),
    )
    out = financial_total_agreement(xml, pdf)
    assert out["old_abs_pct_error"] == 0.0
    assert out["xml_old_total"] == 100


# --- modified_section_overlap ------------------------------------------


def test_modified_section_overlap_all_paths_match_returns_one():
    xml = _diff(
        _node(("a",), "modified", old_text="old A", new_text="new A text"),
        _node(("b",), "modified", old_text="old B", new_text="new B text"),
    )
    pdf = _diff(
        _node(("a",), "modified", old_text="old A", new_text="new A text"),
        _node(("b",), "modified", old_text="old B", new_text="new B text"),
    )
    assert modified_section_overlap(xml, pdf) == 1.0


def test_modified_section_overlap_half_matched_returns_half():
    xml = _diff(
        _node(("a",), "modified", old_text="old A", new_text="new A body content goes here"),
        _node(("b",), "modified", old_text="old B", new_text="new B body content goes here"),
    )
    pdf = _diff(
        _node(("a",), "modified", old_text="old A", new_text="new A body content goes here"),
    )
    assert modified_section_overlap(xml, pdf) == 0.5


def test_modified_section_overlap_no_xml_modified_is_vacuously_one():
    xml = _diff(_node(("a",), "unchanged"))
    pdf = _diff(_node(("a",), "modified", old_text="x", new_text="y"))
    assert modified_section_overlap(xml, pdf) == 1.0


def test_modified_section_overlap_falls_back_to_section_number_match():
    """When match_paths differ but section_number is the same and body
    text matches, count it as covered."""
    xml = _diff(
        _node(
            ("title-i", "sec. 101"),
            "modified",
            old_text="...",
            new_text="The Secretary shall report annually.",
            section_number="Sec. 101",
        )
    )
    pdf = _diff(
        _node(
            ("untitled", "office-of-the-secretary", "sec. 101"),
            "modified",
            old_text="...",
            new_text="The Secretary shall report annually.",
            section_number="Sec. 101",
        )
    )
    assert modified_section_overlap(xml, pdf) == 1.0


def test_modified_section_overlap_below_similarity_threshold_not_covered():
    xml = _diff(_node(("a",), "modified", old_text="...", new_text="alpha bravo charlie delta echo"))
    pdf = _diff(_node(("a",), "modified", old_text="...", new_text="completely different text"))
    out = modified_section_overlap(xml, pdf, sim_threshold=0.7)
    assert out == 0.0


# --- change_type_jaccard -----------------------------------------------


def test_change_type_jaccard_identical_diffs_is_one():
    xml = _diff(_node(("a",), "modified"), _node(("b",), "added"))
    pdf = _diff(_node(("a",), "modified"), _node(("b",), "added"))
    assert change_type_jaccard(xml, pdf) == 1.0


def test_change_type_jaccard_disjoint_diffs_is_zero():
    xml = _diff(_node(("a",), "modified"))
    pdf = _diff(_node(("b",), "added"))
    assert change_type_jaccard(xml, pdf) == 0.0


def test_change_type_jaccard_partial_overlap():
    xml = _diff(_node(("a",), "modified"), _node(("b",), "added"))
    pdf = _diff(_node(("a",), "modified"), _node(("c",), "removed"))
    # Intersection: {("a",), "modified"}; Union: 3 distinct keys
    assert change_type_jaccard(xml, pdf) == 1 / 3


def test_change_type_jaccard_both_empty_is_one():
    xml = _diff()
    pdf = _diff()
    assert change_type_jaccard(xml, pdf) == 1.0


# --- unpair_rate -------------------------------------------------------


def test_unpair_rate_all_unchanged_is_zero():
    """No changes between versions -> nothing to unpair."""
    diff = _diff(_node(("a",), "unchanged"), _node(("b",), "unchanged"))
    assert unpair_rate(diff) == 0.0


def test_unpair_rate_all_added_is_one():
    """Every node is on one side only -> 100% unpaired."""
    diff = _diff(_node(("a",), "added"), _node(("b",), "added"))
    assert unpair_rate(diff) == 1.0


def test_unpair_rate_mixed_returns_unpaired_fraction():
    """2 added + 1 modified + 1 unchanged = 2/4 unpaired."""
    diff = _diff(
        _node(("a",), "added"),
        _node(("b",), "added"),
        _node(("c",), "modified"),
        _node(("d",), "unchanged"),
    )
    assert unpair_rate(diff) == 0.5


def test_unpair_rate_empty_diff_is_vacuous_zero():
    """No nodes at all -> nothing was unpaired (vacuous). Caller should
    sanity-check the diff isn't empty before relying on the metric."""
    assert unpair_rate(_diff()) == 0.0


def test_unpair_rate_modified_and_moved_count_as_paired():
    """All change types except added / removed represent successful
    pairing. ``moved`` reflects a section the matcher relocated --
    still paired."""
    diff = _diff(
        _node(("a",), "modified"),
        _node(("b",), "moved"),
        _node(("c",), "added"),
    )
    # 2 paired (modified + moved), 1 unpaired (added) -> 1/3
    assert unpair_rate(diff) == 1 / 3
