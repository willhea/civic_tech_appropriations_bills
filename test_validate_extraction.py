"""Validate extracted bill amounts against independently curated spreadsheet data.

These tests compare dollar amounts extracted by our parser from enrolled bill
XML against amounts from a hand-curated Legislative Branch appropriations
spreadsheet covering FY2014-FY2020 across 7 bills and both chambers.

This catches bugs in amount extraction, node assignment, and tree structure
that internal-only tests cannot detect.
"""

import json
from pathlib import Path

import pytest

from bill_tree import normalize_bill
from diff_bill import extract_amounts

pytestmark = pytest.mark.slow

FIXTURE_PATH = Path("test_data/validation_leg_branch.json")


def _load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


skip_if_missing = pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="Validation fixture not present",
)


@skip_if_missing
class TestLegBranchValidation:
    """Validate Legislative Branch appropriations across multiple bills."""

    @pytest.fixture(scope="class")
    def fixture_data(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def bill_trees(self, fixture_data):
        """Load each unique bill once."""
        trees = {}
        for account in fixture_data["accounts"]:
            bill = account["bill"]
            version = account["version"]
            if bill not in trees:
                # Find the enrolled bill XML
                bill_dir = Path("bills") / bill
                xml_path = bill_dir / version
                if xml_path.exists():
                    trees[bill] = normalize_bill(xml_path)
        return trees

    def test_all_bills_loaded(self, fixture_data, bill_trees):
        """Every bill referenced in the fixture should be loadable."""
        expected_bills = set(a["bill"] for a in fixture_data["accounts"])
        missing = expected_bills - set(bill_trees.keys())
        assert missing == set(), f"Could not load bills: {missing}"

    def test_all_nodes_found(self, fixture_data, bill_trees):
        """Every fixture account should have a corresponding node."""
        missing = []
        for account in fixture_data["accounts"]:
            tree = bill_trees.get(account["bill"])
            if tree is None:
                continue
            path = tuple(account["match_path"])
            found = any(n.match_path == path for n in tree.nodes)
            if not found:
                missing.append(f"{account['fy']} {account['chamber']}: {account['excel_name']} -> {path}")
        assert missing == [], f"{len(missing)} nodes not found:\n" + "\n".join(f"  {m}" for m in missing[:10])

    def test_all_amounts_match(self, fixture_data, bill_trees):
        """Every fixture amount should appear in the node's extracted amounts."""
        mismatches = []
        for account in fixture_data["accounts"]:
            tree = bill_trees.get(account["bill"])
            if tree is None:
                continue
            path = tuple(account["match_path"])
            expected = account["expected_amount"]
            node = next((n for n in tree.nodes if n.match_path == path), None)
            if node is None:
                continue  # caught by test_all_nodes_found
            extracted = extract_amounts(node.body_text)
            if expected not in extracted:
                mismatches.append(
                    f"{account['fy']} {account['chamber']}: {account['excel_name']} "
                    f"expected ${expected:,}, got {['${:,}'.format(a) for a in extracted]}"
                )
        assert mismatches == [], f"{len(mismatches)} mismatches:\n" + "\n".join(f"  {m}" for m in mismatches[:10])

    def test_covers_multiple_bills(self, fixture_data):
        """Fixture should cover multiple bills for meaningful validation."""
        bills = set(a["bill"] for a in fixture_data["accounts"])
        assert len(bills) >= 5

    def test_covers_both_chambers(self, fixture_data):
        """Fixture should cover both House and Senate."""
        chambers = set(a["chamber"] for a in fixture_data["accounts"])
        assert chambers == {"house", "senate"}

    def test_validation_count(self, fixture_data):
        """Fixture has a meaningful number of entries."""
        assert len(fixture_data["accounts"]) >= 300
