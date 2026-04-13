"""Tests for financial change extraction in diff_bill."""

from diff_bill import (
    FinancialChange,
    compute_financial_change,
    extract_amounts,
    financial_change_to_dict,
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
            "For expenses, $64,560,558,000: Provided, That not to exceed "
            "$7,000,000 shall be available for emergencies."
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
            old_text="For acquisition and construction, $2,022,775,000, to remain available until September 30, 2025.",
            new_text="For acquisition, construction, and improvement, $2,022,775,000, to remain available until expended.",
        )
        assert result is not None
        assert result.amounts_changed is False
        assert result.old_amounts == result.new_amounts


class TestFinancialChangeToDict:
    def test_serialize(self):
        fc = FinancialChange(
            old_amounts=(1876875000,),
            new_amounts=(2022775000,),
            amounts_changed=True,
        )
        result = financial_change_to_dict(fc)
        assert result == {
            "old_amounts": [1876875000],
            "new_amounts": [2022775000],
            "amounts_changed": True,
        }

    def test_serialize_empty_amounts(self):
        fc = FinancialChange(
            old_amounts=(),
            new_amounts=(5000000,),
            amounts_changed=True,
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


class TestCliFinancial:
    def test_financial_flag_filters_output(self):
        import json
        import subprocess

        result = subprocess.run(
            [
                "uv", "run", "python", "diff_bill.py", "compare",
                "output/118-hr-8774/1_reported-in-house.xml",
                "output/118-hr-8774/2_engrossed-in-house.xml",
                "--financial",
            ],
            capture_output=True, text=True,
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
                "uv", "run", "python", "diff_bill.py", "compare",
                "output/118-hr-8774/1_reported-in-house.xml",
                "output/118-hr-8774/2_engrossed-in-house.xml",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)

        assert "financial_summary" not in data
        for change in data["changes"]:
            assert "financial" not in change


class TestIntegrationFinancial:
    """Integration tests against real bill XML files."""

    HR4366_V1 = "output/118-hr-4366/1_reported-in-house.xml"
    HR4366_V6 = "output/118-hr-4366/6_enrolled-bill.xml"

    @staticmethod
    def _skip_if_missing(*paths):
        import os
        for p in paths:
            if not os.path.exists(p):
                import pytest
                pytest.skip(f"Test XML not found: {p}")

    def test_milcon_army_amounts_changed(self):
        from pathlib import Path
        from bill_tree import normalize_bill
        from diff_bill import diff_bills

        self._skip_if_missing(self.HR4366_V1, self.HR4366_V6)

        old = normalize_bill(Path(self.HR4366_V1))
        new = normalize_bill(Path(self.HR4366_V6))
        result = diff_bills(old, new)

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

    def test_financial_filter_reduces_output(self):
        from pathlib import Path
        from bill_tree import normalize_bill
        from diff_bill import diff_bills, bill_diff_to_dict

        self._skip_if_missing(self.HR4366_V1, self.HR4366_V6)

        old = normalize_bill(Path(self.HR4366_V1))
        new = normalize_bill(Path(self.HR4366_V6))
        result = diff_bills(old, new)

        all_changes = bill_diff_to_dict(result)
        financial_only = bill_diff_to_dict(result, financial=True)

        total = len(all_changes["changes"])
        with_amounts = len([
            c for c in financial_only["changes"]
            if "financial" in c and c["financial"]["amounts_changed"]
        ])
        assert with_amounts < total
        assert with_amounts > 0
