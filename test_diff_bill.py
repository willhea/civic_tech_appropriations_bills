import json
import subprocess
from pathlib import Path

import pytest

from bill_tree import BillNode, BillTree, normalize_bill
from diff_bill import BillDiff, NodeDiff, bill_diff_to_dict, diff_bills, diff_text, match_nodes


def _node(match_path, body_text="text", element_id="", header_text="", tag="appropriations-intermediate"):
    """Helper to build a BillNode with defaults for testing."""
    return BillNode(
        match_path=match_path,
        display_path=match_path,  # use match_path as display_path for simplicity
        tag=tag,
        element_id=element_id,
        header_text=header_text,
        body_text=body_text,
        section_number="",
    )


def _tree(nodes):
    """Helper to build a BillTree with defaults."""
    return BillTree(congress=118, bill_type="hr", bill_number=4366, version="test", nodes=nodes)


class TestMatchNodes:
    def test_all_matched(self):
        """Nodes with same match_path in both versions pair up."""
        old = _tree([_node(("a", "b"), "old text")])
        new = _tree([_node(("a", "b"), "new text")])
        pairs = match_nodes(old, new)
        assert len(pairs) == 1
        old_node, new_node = pairs[0]
        assert old_node is not None
        assert new_node is not None
        assert old_node.body_text == "old text"
        assert new_node.body_text == "new text"

    def test_added_nodes(self):
        """Nodes only in new version appear as (None, new_node)."""
        old = _tree([])
        new = _tree([_node(("a", "b"), "added")])
        pairs = match_nodes(old, new)
        assert len(pairs) == 1
        assert pairs[0][0] is None
        assert pairs[0][1].body_text == "added"

    def test_removed_nodes(self):
        """Nodes only in old version appear as (old_node, None)."""
        old = _tree([_node(("a", "b"), "removed")])
        new = _tree([])
        pairs = match_nodes(old, new)
        assert len(pairs) == 1
        assert pairs[0][0].body_text == "removed"
        assert pairs[0][1] is None

    def test_mixed_matched_added_removed(self):
        """Mix of matched, added, and removed nodes."""
        old = _tree([
            _node(("shared",), "old shared"),
            _node(("only_old",), "removed"),
        ])
        new = _tree([
            _node(("shared",), "new shared"),
            _node(("only_new",), "added"),
        ])
        pairs = match_nodes(old, new)
        assert len(pairs) == 3

        # Find each type
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        added = [(o, n) for o, n in pairs if o is None]
        removed = [(o, n) for o, n in pairs if n is None]
        assert len(matched) == 1
        assert len(added) == 1
        assert len(removed) == 1

    def test_duplicate_paths_matched_by_position(self):
        """Multiple nodes with same match_path are paired by position order."""
        old = _tree([
            _node(("dup",), "old first"),
            _node(("dup",), "old second"),
        ])
        new = _tree([
            _node(("dup",), "new first"),
            _node(("dup",), "new second"),
        ])
        pairs = match_nodes(old, new)
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        assert len(matched) == 2
        assert matched[0][0].body_text == "old first"
        assert matched[0][1].body_text == "new first"
        assert matched[1][0].body_text == "old second"
        assert matched[1][1].body_text == "new second"

    def test_uneven_duplicates(self):
        """When one side has more duplicates, extras show as added/removed."""
        old = _tree([_node(("dup",), "old")])
        new = _tree([
            _node(("dup",), "new first"),
            _node(("dup",), "new second"),
        ])
        pairs = match_nodes(old, new)
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        added = [(o, n) for o, n in pairs if o is None]
        assert len(matched) == 1
        assert len(added) == 1


REPORTED_BILL_PATH = Path("bills/118-hr-4366/1_reported-in-house.xml")
ENROLLED_BILL_PATH = Path("bills/118-hr-4366/6_enrolled-bill.xml")


@pytest.mark.skipif(
    not REPORTED_BILL_PATH.exists() or not ENROLLED_BILL_PATH.exists(),
    reason="Real XML not present",
)
class TestMatchNodesIntegration:
    """Integration: match nodes across structurally different versions."""

    def test_cross_structural_matching(self):
        """v1 (no divisions) and v6 (with divisions) share 'military construction, army'."""
        old = normalize_bill(REPORTED_BILL_PATH)
        new = normalize_bill(ENROLLED_BILL_PATH)
        pairs = match_nodes(old, new)

        army_path = ("department of defense", "military construction, army")
        army_pairs = [
            (o, n) for o, n in pairs
            if o is not None and n is not None and o.match_path == army_path
        ]
        assert len(army_pairs) == 1

    def test_new_divisions_show_as_added(self):
        """Divisions in v6 that don't exist in v1 produce added nodes."""
        old = normalize_bill(REPORTED_BILL_PATH)
        new = normalize_bill(ENROLLED_BILL_PATH)
        pairs = match_nodes(old, new)

        added = [(o, n) for o, n in pairs if o is None and n is not None]
        added_paths = {n.match_path for _, n in added}
        agriculture_added = [p for p in added_paths if "agriculture" in str(p).lower()]
        assert len(agriculture_added) > 0


class TestDiffText:
    def test_identical_text_returns_empty(self):
        assert diff_text("same text", "same text") == []

    def test_changed_text_returns_diff_lines(self):
        lines = diff_text(
            "For expenses, $1,000,000, to remain available.",
            "For expenses, $2,000,000, to remain available.",
        )
        assert len(lines) > 0
        # Should contain unified diff markers
        assert any(line.startswith("-") for line in lines)
        assert any(line.startswith("+") for line in lines)

    def test_multiline_diff(self):
        old = "Line one.\nLine two.\nLine three."
        new = "Line one.\nLine modified.\nLine three."
        lines = diff_text(old, new)
        assert any("two" in line for line in lines)
        assert any("modified" in line for line in lines)


class TestDiffBills:
    def test_modified_node(self):
        old = _tree([_node(("a",), "old text", element_id="E1")])
        new = _tree([_node(("a",), "new text", element_id="E2")])
        result = diff_bills(old, new)
        assert result.summary["modified"] == 1
        assert result.summary["unchanged"] == 0
        assert len(result.changes) == 1
        change = result.changes[0]
        assert change.change_type == "modified"
        assert change.old_text == "old text"
        assert change.new_text == "new text"
        assert change.element_id_old == "E1"
        assert change.element_id_new == "E2"
        assert len(change.text_diff) > 0

    def test_unchanged_node(self):
        old = _tree([_node(("a",), "same")])
        new = _tree([_node(("a",), "same")])
        result = diff_bills(old, new)
        assert result.summary["unchanged"] == 1
        assert result.summary["modified"] == 0

    def test_dissimilar_match_becomes_removed_plus_added(self):
        """When matched texts are completely different, treat as removed + added."""
        old = _tree([_node(
            ("dept", "sec. 129"),
            "For an additional amount for Military Construction, Air Force, "
            "$252,000,000, to remain available until September 30, 2028, "
            "for expenses incurred as a result of natural disasters.",
        )])
        new = _tree([_node(
            ("dept", "sec. 129"),
            "For an additional amount for the accounts and in the amounts "
            "specified for planning and design and unspecified minor construction "
            "for construction improvements to Department of Defense laboratory facilities.",
        )])
        result = diff_bills(old, new)
        # These are completely different provisions sharing a section number.
        # Should be split into removed + added, not reported as modified.
        assert result.summary["modified"] == 0
        assert result.summary["added"] == 1
        assert result.summary["removed"] == 1

    def test_similar_match_stays_modified(self):
        """When matched texts are similar (e.g., just an amount change), keep as modified."""
        old = _tree([_node(
            ("dept", "military construction, army"),
            "For acquisition, construction, installation, $1,876,875,000, "
            "to remain available until September 30, 2028.",
        )])
        new = _tree([_node(
            ("dept", "military construction, army"),
            "For acquisition, construction, installation, $2,022,775,000, "
            "to remain available until September 30, 2028.",
        )])
        result = diff_bills(old, new)
        assert result.summary["modified"] == 1
        assert result.summary["added"] == 0
        assert result.summary["removed"] == 0

    def test_added_and_removed(self):
        old = _tree([_node(("removed",), "gone")])
        new = _tree([_node(("added",), "new")])
        result = diff_bills(old, new)
        assert result.summary["added"] == 1
        assert result.summary["removed"] == 1
        added = [c for c in result.changes if c.change_type == "added"]
        removed = [c for c in result.changes if c.change_type == "removed"]
        assert added[0].old_text is None
        assert added[0].new_text == "new"
        assert removed[0].old_text == "gone"
        assert removed[0].new_text is None

    def test_metadata_propagated(self):
        old = BillTree(congress=118, bill_type="hr", bill_number=4366, version="v1", nodes=[])
        new = BillTree(congress=118, bill_type="hr", bill_number=4366, version="v2", nodes=[])
        result = diff_bills(old, new)
        assert result.old_version == "v1"
        assert result.new_version == "v2"
        assert result.congress == 118
        assert result.bill_type == "hr"
        assert result.bill_number == 4366


class TestBillDiffToDict:
    def test_schema(self):
        diff = BillDiff(
            old_version="v1",
            new_version="v2",
            congress=118,
            bill_type="hr",
            bill_number=4366,
            summary={"added": 1, "removed": 0, "modified": 0, "unchanged": 0},
            changes=[
                NodeDiff(
                    display_path_old=None,
                    display_path_new=("DEPT", "Account"),
                    match_path=("dept", "account"),
                    change_type="added",
                    old_text=None,
                    new_text="For expenses, $1,000.",
                    text_diff=None,
                    section_number="",
                    element_id_old="",
                    element_id_new="E1",
                ),
            ],
        )
        d = bill_diff_to_dict(diff)
        assert d["old_version"] == "v1"
        assert d["new_version"] == "v2"
        assert d["congress"] == 118
        assert d["summary"]["added"] == 1
        assert len(d["changes"]) == 1
        change = d["changes"][0]
        assert change["display_path_old"] is None
        assert change["display_path_new"] == ["DEPT", "Account"]
        assert change["match_path"] == ["dept", "account"]
        assert change["change_type"] == "added"
        assert change["new_text"] == "For expenses, $1,000."


@pytest.mark.skipif(
    not REPORTED_BILL_PATH.exists() or not ENROLLED_BILL_PATH.exists(),
    reason="Real XML not present",
)
class TestCli:
    def test_compare_to_stdout(self):
        result = subprocess.run(
            ["uv", "run", "python", "diff_bill.py", "compare",
             str(REPORTED_BILL_PATH), str(ENROLLED_BILL_PATH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "changes" in data
        assert data["summary"]["added"] > 0

    def test_compare_to_file(self, tmp_path):
        out = tmp_path / "diff.json"
        result = subprocess.run(
            ["uv", "run", "python", "diff_bill.py", "compare",
             str(REPORTED_BILL_PATH), str(ENROLLED_BILL_PATH),
             "-o", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text())
        assert data["old_version"] == "reported-in-house"
        assert data["new_version"] == "enrolled-bill"

    def test_filter_flag(self):
        result = subprocess.run(
            ["uv", "run", "python", "diff_bill.py", "compare",
             str(REPORTED_BILL_PATH), str(ENROLLED_BILL_PATH),
             "--filter", "military construction, army"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # All changes should contain "military construction, army" in match_path
        for change in data["changes"]:
            path_str = " ".join(change["match_path"])
            assert "military construction, army" in path_str


@pytest.mark.skipif(
    not REPORTED_BILL_PATH.exists() or not ENROLLED_BILL_PATH.exists(),
    reason="Real XML not present",
)
class TestEndToEnd:
    """Full pipeline: normalize both versions, diff, verify results."""

    def test_v1_to_v6_diff(self):
        old = normalize_bill(REPORTED_BILL_PATH)
        new = normalize_bill(ENROLLED_BILL_PATH)
        result = diff_bills(old, new)

        # Should have all four change types
        assert result.summary["added"] > 0
        assert result.summary["modified"] > 0
        # Some sections unchanged between MilCon-VA versions
        assert result.summary["unchanged"] >= 0

        # Military construction, army should be modified (amount changed)
        army_changes = [
            c for c in result.changes
            if c.match_path == ("department of defense", "military construction, army")
        ]
        assert len(army_changes) == 1
        assert army_changes[0].change_type == "modified"
        assert army_changes[0].text_diff is not None

        # Agriculture content should be added (not in v1, present in v6)
        added_changes = [c for c in result.changes if c.change_type == "added"]
        added_paths_str = [" ".join(c.match_path) for c in added_changes]
        assert any("agriculture" in p for p in added_paths_str)

    def test_v1_to_v6_json_roundtrip(self):
        old = normalize_bill(REPORTED_BILL_PATH)
        new = normalize_bill(ENROLLED_BILL_PATH)
        result = diff_bills(old, new)
        d = bill_diff_to_dict(result)
        # Verify it's JSON-serializable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["congress"] == 118
        assert len(parsed["changes"]) == len(result.changes)
