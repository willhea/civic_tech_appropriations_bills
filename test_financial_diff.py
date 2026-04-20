"""Tests for financial change extraction in diff_bill."""

from pathlib import Path

import pytest

from diff_bill import (
    FinancialChange,
    compute_financial_change,
    extract_amounts,
    financial_change_to_dict,
    match_amounts,
)


class TestExtractAmounts:
    def test_single_amount(self):
        text = "For construction, $2,022,775,000, to remain available until expended."
        assert extract_amounts(text) == (2022775000,)

    def test_empty_string(self):
        assert extract_amounts("") == ()

    def test_no_dollar_amounts(self):
        text = "None of the funds may be used for any purpose other than authorized."
        assert extract_amounts(text) == ()

    def test_zero_amount_filtered(self):
        text = "appropriation estimated at $0: Provided further, $5,000,000 for operations."
        result = extract_amounts(text)
        assert result == (5000000,)

    def test_two_amounts_in_order(self):
        text = (
            "For expenses, $64,560,558,000: Provided, That not to exceed $7,000,000 shall be available for emergencies."
        )
        assert extract_amounts(text) == (64560558000, 7000000)

    def test_three_amounts(self):
        text = (
            "$15,072,388,000, which shall be in addition to funds previously "
            "appropriated under this heading: Provided, That $71,000,000,000 "
            "shall become available on October 1, 2024: Provided further, That "
            "$3,034,205,000 is hereby rescinded."
        )
        assert extract_amounts(text) == (15072388000, 71000000000, 3034205000)

    def test_amendment_increased_reduced_stripped(self):
        text = (
            "For construction, $1,517,455,000 "
            "(increased by $103,000,000) (reduced by $103,000,000), "
            "to remain available until September 30, 2028."
        )
        assert extract_amounts(text) == (1517455000,)

    def test_multiple_amendment_annotations_stripped(self):
        text = (
            "For operating expenses, $3,899,000,000: "
            "$3,899,000,000 (reduced by $1,000,000) "
            "(increased by $1,000,000) (reduced by $1,000,000) "
            "(increased by $1,000,000) (reduced by $1,000,000) "
            "(increased by $1,000,000) (increased by $10,000,000)"
            "(reduced by $10,000,000): Provided, That expenses."
        )
        assert extract_amounts(text) == (3899000000, 3899000000)

    def test_single_amendment_stripped(self):
        text = "For expenses, $500,000 (increased by $200,000), to remain."
        assert extract_amounts(text) == (500000,)

    def test_non_amendment_parenthetical_kept(self):
        text = "For expenses, $500,000 (not to exceed $100,000) for operations."
        assert extract_amounts(text) == (500000, 100000)


class TestComputeFinancialChange:
    def test_amounts_changed(self):
        result = compute_financial_change(
            old_text="For construction, $1,876,875,000, to remain available.",
            new_text="For construction, $2,022,775,000, to remain available.",
        )
        assert result is not None
        assert result.amounts_changed is True
        assert result.old_amounts == (1876875000,)
        assert result.new_amounts == (2022775000,)
        assert result.paired_amounts == ((1876875000, 2022775000),)

    def test_amounts_unchanged(self):
        result = compute_financial_change(
            old_text="For expenses, $5,000,000, to remain available.",
            new_text="For expenses, $5,000,000, to remain available until expended.",
        )
        assert result is not None
        assert result.amounts_changed is False

    def test_added_section_with_amounts(self):
        result = compute_financial_change(
            old_text=None,
            new_text="For construction, $2,022,775,000, to remain available.",
        )
        assert result is not None
        assert result.amounts_changed is True
        assert result.old_amounts == ()
        assert result.new_amounts == (2022775000,)
        assert result.paired_amounts == ((None, 2022775000),)

    def test_removed_section_with_amounts(self):
        result = compute_financial_change(
            old_text="For construction, $1,876,875,000, to remain available.",
            new_text=None,
        )
        assert result is not None
        assert result.amounts_changed is True
        assert result.old_amounts == (1876875000,)
        assert result.new_amounts == ()

    def test_no_amounts_either_side(self):
        result = compute_financial_change(
            old_text="None of the funds shall be used for lobbying.",
            new_text="None of the funds shall be used for lobbying activities.",
        )
        assert result is None

    def test_both_none(self):
        assert compute_financial_change(None, None) is None

    def test_text_changed_amounts_same(self):
        """Text modified but dollar amounts identical -- not a financial change."""
        result = compute_financial_change(
            old_text=(
                "For acquisition and construction, $2,022,775,000, to remain available until September 30, 2025."
            ),
            new_text=(
                "For acquisition, construction, and improvement, $2,022,775,000, to remain available until expended."
            ),
        )
        assert result is not None
        assert result.amounts_changed is False
        assert result.old_amounts == result.new_amounts

    def test_amendment_annotation_detected(self):
        """Floor amendment annotations like (increased by $X) should be flagged."""
        result = compute_financial_change(
            old_text="For expenses, $287,000,000.",
            new_text="For expenses, $287,000,000 (increased by $2,000,000).",
        )
        assert result is not None
        assert result.has_amendment_annotations is True

    def test_no_amendment_annotation(self):
        """Text without amendment annotations should not be flagged."""
        result = compute_financial_change(
            old_text="For expenses, $287,000,000.",
            new_text="For expenses, $289,000,000.",
        )
        assert result is not None
        assert result.has_amendment_annotations is False

    def test_annotation_without_base_change_not_flagged(self):
        """Annotations alone should not flag amounts_changed.

        Annotations reference the budget request baseline, not the previous
        bill version. The base amount ($287M) is the real appropriation.
        """
        result = compute_financial_change(
            old_text="For expenses, $287,000,000.",
            new_text="For expenses, $287,000,000 (increased by $2,000,000).",
        )
        assert result is not None
        assert result.has_amendment_annotations is True
        assert result.amounts_changed is False


class TestFinancialChangeToDict:
    def test_serialize(self):
        fc = FinancialChange(
            old_amounts=(1876875000,),
            new_amounts=(2022775000,),
            amounts_changed=True,
            paired_amounts=((1876875000, 2022775000),),
        )
        result = financial_change_to_dict(fc)
        assert result == {
            "old_amounts": [1876875000],
            "new_amounts": [2022775000],
            "amounts_changed": True,
            "paired_amounts": [[1876875000, 2022775000]],
            "has_amendment_annotations": False,
        }

    def test_serialize_empty_amounts(self):
        fc = FinancialChange(
            old_amounts=(),
            new_amounts=(5000000,),
            amounts_changed=True,
            paired_amounts=((None, 5000000),),
        )
        result = financial_change_to_dict(fc)
        assert result["old_amounts"] == []
        assert result["new_amounts"] == [5000000]


class TestBillDiffToDictFinancial:
    def test_financial_flag_adds_financial_key(self):
        from diff_bill import BillDiff, NodeDiff, bill_diff_to_dict

        diff = BillDiff(
            old_version="v1",
            new_version="v2",
            congress=118,
            bill_type="hr",
            bill_number=4366,
            summary={"added": 0, "removed": 0, "modified": 1, "unchanged": 0},
            changes=[
                NodeDiff(
                    display_path_old=("Title I", "Army"),
                    display_path_new=("Title I", "Army"),
                    match_path=("title i", "army"),
                    change_type="modified",
                    old_text="For construction, $1,000,000.",
                    new_text="For construction, $2,000,000.",
                    text_diff=["- $1,000,000", "+ $2,000,000"],
                    section_number="",
                    element_id_old="a",
                    element_id_new="b",
                ),
            ],
        )
        result = bill_diff_to_dict(diff, financial=True)
        assert "financial" in result["changes"][0]
        assert result["changes"][0]["financial"]["amounts_changed"] is True
        assert "financial_summary" in result

    def test_no_financial_flag_no_financial_key(self):
        from diff_bill import BillDiff, NodeDiff, bill_diff_to_dict

        diff = BillDiff(
            old_version="v1",
            new_version="v2",
            congress=118,
            bill_type="hr",
            bill_number=4366,
            summary={"added": 0, "removed": 0, "modified": 1, "unchanged": 0},
            changes=[
                NodeDiff(
                    display_path_old=("Title I", "Army"),
                    display_path_new=("Title I", "Army"),
                    match_path=("title i", "army"),
                    change_type="modified",
                    old_text="For construction, $1,000,000.",
                    new_text="For construction, $2,000,000.",
                    text_diff=["- $1,000,000", "+ $2,000,000"],
                    section_number="",
                    element_id_old="a",
                    element_id_new="b",
                ),
            ],
        )
        result = bill_diff_to_dict(diff)
        assert "financial" not in result["changes"][0]
        assert "financial_summary" not in result


_HR8774_V1 = Path("bills/118-hr-8774/1_reported-in-house.xml")
_HR8774_V2 = Path("bills/118-hr-8774/2_engrossed-in-house.xml")


@pytest.mark.slow
@pytest.mark.skipif(
    not _HR8774_V1.exists() or not _HR8774_V2.exists(),
    reason="Real XML not present",
)
class TestCliFinancial:
    def test_financial_flag_filters_output(self):
        import json
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "diff_bill.py",
                "compare",
                "bills/118-hr-8774/1_reported-in-house.xml",
                "bills/118-hr-8774/2_engrossed-in-house.xml",
                "--format",
                "json",
                "--financial",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)

        for change in data["changes"]:
            assert "financial" in change
            assert change["financial"]["amounts_changed"] is True

        assert "financial_summary" in data
        assert data["financial_summary"]["sections_with_financial_changes"] > 0
        assert data["financial_summary"]["sections_with_financial_changes"] == len(data["changes"])

    def test_no_financial_flag_no_filtering(self):
        import json
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "diff_bill.py",
                "compare",
                "bills/118-hr-8774/1_reported-in-house.xml",
                "bills/118-hr-8774/2_engrossed-in-house.xml",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)

        assert "financial_summary" not in data
        for change in data["changes"]:
            assert "financial" not in change


@pytest.mark.slow
class TestAmountSanityChecks:
    """Sanity checks on extracted amounts from real bill XML."""

    def test_nodes_with_amounts_count(self, hr4366_v6):
        count = sum(1 for n in hr4366_v6.nodes if extract_amounts(n.body_text))
        assert count == 567

    def test_all_amounts_in_valid_range(self, hr4366_v6):
        for node in hr4366_v6.nodes:
            for amount in extract_amounts(node.body_text):
                assert 1 <= amount <= 999_999_999_999, f"Amount ${amount:,} out of range at {node.match_path}"

    def test_no_node_exceeds_max_amounts(self, hr4366_v6):
        for node in hr4366_v6.nodes:
            amounts = extract_amounts(node.body_text)
            assert len(amounts) <= 70, f"Node {node.match_path} has {len(amounts)} amounts (max 70)"


@pytest.mark.slow
class TestIntegrationFinancial:
    """Integration tests against real bill XML files."""

    def test_milcon_army_amounts_changed(self, hr4366_v1_v6_diff):
        result = hr4366_v1_v6_diff

        milcon = None
        for c in result.changes:
            if c.match_path and "military construction, army" in " ".join(c.match_path):
                milcon = c
                break

        assert milcon is not None, "Military construction, army not found in diff"
        fc = compute_financial_change(milcon.old_text, milcon.new_text)
        assert fc is not None
        assert fc.amounts_changed is True
        assert 2022775000 in fc.new_amounts
        assert any(v > 1_000_000_000 for v in fc.old_amounts)

    def test_financial_filter_reduces_output(self, hr4366_v1_v6_diff):
        from diff_bill import bill_diff_to_dict

        result = hr4366_v1_v6_diff

        all_changes = bill_diff_to_dict(result)
        financial_only = bill_diff_to_dict(result, financial=True)

        total = len(all_changes["changes"])
        with_amounts = len(
            [c for c in financial_only["changes"] if "financial" in c and c["financial"]["amounts_changed"]]
        )
        assert with_amounts < total
        assert with_amounts > 0


class TestMatchAmounts:
    def test_identical_texts(self):
        """All amounts pair with themselves when text is identical."""
        text = "For expenses, $5,000,000: Provided, That $1,000,000 shall be for operations."
        pairs = match_amounts(text, text)
        assert pairs == [(5000000, 5000000), (1000000, 1000000)]

    def test_inserted_amount(self):
        """New proviso inserted mid-text: appears as (None, new), others pair correctly."""
        old = "For expenses, $5,000,000: Provided, That $3,000,000 shall be for operations."
        new = (
            "For expenses, $5,000,000: Provided, That $2,000,000 "
            "shall remain available until September 30, 2028: "
            "Provided further, That $3,000,000 shall be for operations."
        )
        pairs = match_amounts(old, new)
        assert pairs == [(5000000, 5000000), (None, 2000000), (3000000, 3000000)]

    def test_removed_amount(self):
        """Proviso removed: its amount appears as (old, None)."""
        old = (
            "For expenses, $5,000,000: Provided, That $2,000,000 "
            "shall remain available: Provided further, That "
            "$3,000,000 shall be for operations."
        )
        new = "For expenses, $5,000,000: Provided, That $3,000,000 shall be for operations."
        pairs = match_amounts(old, new)
        assert pairs == [(5000000, 5000000), (2000000, None), (3000000, 3000000)]

    def test_changed_amount_same_context(self):
        """Amount value changes but surrounding text stays: paired as (old, new)."""
        old = "For construction, $1,876,875,000, to remain available until September 30, 2028."
        new = "For construction, $2,022,775,000, to remain available until September 30, 2028."
        pairs = match_amounts(old, new)
        assert pairs == [(1876875000, 2022775000)]

    def test_both_none(self):
        """Both texts None returns empty list."""
        assert match_amounts(None, None) == []

    def test_old_none_added_section(self):
        """Old text None (added section): all amounts as (None, new)."""
        pairs = match_amounts(None, "For expenses, $5,000,000, to remain available.")
        assert pairs == [(None, 5000000)]

    def test_new_none_removed_section(self):
        """New text None (removed section): all amounts as (old, None)."""
        pairs = match_amounts("For expenses, $5,000,000, to remain available.", None)
        assert pairs == [(5000000, None)]

    def test_replace_block_multiple_amounts(self):
        """Amounts in a rewritten clause pair positionally within the block."""
        old = "For A, $1,000,000 and $2,000,000 for purposes."
        new = "For A, $3,000,000 and $4,000,000 for purposes."
        pairs = match_amounts(old, new)
        assert pairs == [(1000000, 3000000), (2000000, 4000000)]

    def test_no_amounts_either_side(self):
        """No dollar amounts in either text returns empty list."""
        pairs = match_amounts("No amounts here.", "Still no amounts.")
        assert pairs == []

    def test_amendment_annotations_stripped(self):
        """Amendment annotations are stripped before matching."""
        old = "For expenses, $5,000,000 (increased by $1,000,000), to remain."
        new = "For expenses, $5,000,000, to remain."
        pairs = match_amounts(old, new)
        assert pairs == [(5000000, 5000000)]

    def test_zero_amounts_filtered(self):
        """$0 amounts are excluded from pairing."""
        old = "appropriation estimated at $0: Provided, $5,000,000 for ops."
        new = "appropriation estimated at $0: Provided, $7,000,000 for ops."
        pairs = match_amounts(old, new)
        assert pairs == [(5000000, 7000000)]
