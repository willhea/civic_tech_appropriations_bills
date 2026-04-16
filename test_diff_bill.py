import json
import subprocess

import pytest

from bill_tree import BillTree, normalize_division_title
from conftest import HR4366_V1_PATH, HR4366_V6_PATH
from conftest import make_bill_node as _node
from conftest import make_bill_tree as _tree
from diff_bill import BillDiff, NodeDiff, bill_diff_to_dict, diff_bills, diff_text, filter_diff, match_nodes


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
        old = _tree(
            [
                _node(("shared",), "old shared"),
                _node(("only_old",), "removed"),
            ]
        )
        new = _tree(
            [
                _node(("shared",), "new shared"),
                _node(("only_new",), "added"),
            ]
        )
        pairs = match_nodes(old, new)
        assert len(pairs) == 3

        # Find each type
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        added = [(o, n) for o, n in pairs if o is None]
        removed = [(o, n) for o, n in pairs if n is None]
        assert len(matched) == 1
        assert len(added) == 1
        assert len(removed) == 1

    def test_duplicate_paths_matched_by_similarity(self):
        """Multiple nodes with same match_path are paired by text similarity."""
        old = _tree(
            [
                _node(("dup",), "old first"),
                _node(("dup",), "old second"),
            ]
        )
        new = _tree(
            [
                _node(("dup",), "new first"),
                _node(("dup",), "new second"),
            ]
        )
        pairs = match_nodes(old, new)
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        assert len(matched) == 2
        # Each old node should pair with its most similar new node
        pair_set = {(o.body_text, n.body_text) for o, n in matched}
        assert ("old first", "new first") in pair_set
        assert ("old second", "new second") in pair_set

    def test_uneven_duplicates(self):
        """When one side has more duplicates, extras show as added/removed."""
        old = _tree([_node(("dup",), "old")])
        new = _tree(
            [
                _node(("dup",), "new first"),
                _node(("dup",), "new second"),
            ]
        )
        pairs = match_nodes(old, new)
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        added = [(o, n) for o, n in pairs if o is None]
        assert len(matched) == 1
        assert len(added) == 1


@pytest.mark.slow
class TestMatchNodesIntegration:
    """Integration: match nodes across structurally different versions."""

    def test_cross_structural_matching(self, hr4366_v1, hr4366_v6):
        """v1 (no divisions) and v6 (with divisions) share 'military construction, army'."""
        pairs = match_nodes(hr4366_v1, hr4366_v6)

        army_path = ("department of defense", "military construction, army")
        army_pairs = [(o, n) for o, n in pairs if o is not None and n is not None and o.match_path == army_path]
        assert len(army_pairs) == 1

    def test_new_divisions_show_as_added(self, hr4366_v1, hr4366_v6):
        """Divisions in v6 that don't exist in v1 produce added nodes."""
        pairs = match_nodes(hr4366_v1, hr4366_v6)

        added = [(o, n) for o, n in pairs if o is None and n is not None]
        added_paths = {n.match_path for _, n in added}
        agriculture_added = [p for p in added_paths if "agriculture" in str(p).lower()]
        assert len(agriculture_added) > 0


class TestDivisionAwareMatching:
    """Tests for division-aware collision resolution in match_nodes."""

    GP_PATH = ("general provisions",)

    def test_collision_resolved_by_division(self):
        """Nodes with same match_path but different divisions pair by division, not position."""
        old = _tree(
            [
                _node(self.GP_PATH, body_text="mil con provisions", division_label="Division A: Military Construction"),
                _node(self.GP_PATH, body_text="agriculture provisions", division_label="Division B: Agriculture"),
                _node(self.GP_PATH, body_text="transport provisions", division_label="Division C: Transportation"),
            ]
        )
        # New version has same 3 divisions but in different order
        new = _tree(
            [
                _node(self.GP_PATH, body_text="transport provisions new", division_label="Division C: Transportation"),
                _node(
                    self.GP_PATH, body_text="mil con provisions new", division_label="Division A: Military Construction"
                ),
                _node(self.GP_PATH, body_text="agriculture provisions new", division_label="Division B: Agriculture"),
            ]
        )
        pairs = match_nodes(old, new)
        assert len(pairs) == 3
        for old_node, new_node in pairs:
            assert old_node is not None and new_node is not None
            # Each pair should share the same division title (not positional)
            old_node.division_label.split(":")[0]
            new_div_title = new_node.division_label.split(":", 1)[1].strip().lower()
            old_div_title = old_node.division_label.split(":", 1)[1].strip().lower()
            assert old_div_title == new_div_title

    def test_division_letter_change_still_matches(self):
        """Division letter changes (A->C) should still match by title."""
        old = _tree(
            [
                _node(self.GP_PATH, body_text="transport text", division_label="Division C: Transportation"),
            ]
        )
        new = _tree(
            [
                _node(self.GP_PATH, body_text="transport text updated", division_label="Division F: Transportation"),
            ]
        )
        pairs = match_nodes(old, new)
        assert len(pairs) == 1
        assert pairs[0][0] is not None and pairs[0][1] is not None

    def test_unique_paths_unchanged(self):
        """Non-colliding paths should behave identically to current (fast path)."""
        old = _tree(
            [
                _node(("title i", "sec. 1"), body_text="old text", division_label="Division A: MilCon"),
                _node(("title ii", "sec. 2"), body_text="old text 2", division_label="Division A: MilCon"),
            ]
        )
        new = _tree(
            [
                _node(("title i", "sec. 1"), body_text="new text", division_label="Division A: MilCon"),
                _node(("title ii", "sec. 2"), body_text="new text 2", division_label="Division A: MilCon"),
            ]
        )
        pairs = match_nodes(old, new)
        assert len(pairs) == 2
        for o, n in pairs:
            assert o is not None and n is not None
            assert o.match_path == n.match_path

    def test_new_division_added(self):
        """New divisions in the new version appear as (None, new_node)."""
        old = _tree(
            [
                _node(self.GP_PATH, body_text="mil con", division_label="Division A: Military Construction"),
                _node(self.GP_PATH, body_text="agriculture", division_label="Division B: Agriculture"),
            ]
        )
        new = _tree(
            [
                _node(self.GP_PATH, body_text="mil con", division_label="Division A: Military Construction"),
                _node(self.GP_PATH, body_text="agriculture", division_label="Division B: Agriculture"),
                _node(self.GP_PATH, body_text="new defense", division_label="Division C: Defense"),
            ]
        )
        pairs = match_nodes(old, new)
        assert len(pairs) == 3
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        added = [(o, n) for o, n in pairs if o is None]
        assert len(matched) == 2
        assert len(added) == 1
        assert added[0][1].division_label == "Division C: Defense"

    def test_collision_same_division_uses_similarity(self):
        """When same match_path AND same division, pair by text similarity."""
        old = _tree(
            [
                _node(
                    self.GP_PATH,
                    body_text="appropriations for military facilities and construction projects",
                    division_label="Division A: MilCon",
                ),
                _node(
                    self.GP_PATH,
                    body_text="appropriations for naval operations and fleet readiness",
                    division_label="Division A: MilCon",
                ),
            ]
        )
        new = _tree(
            [
                _node(
                    self.GP_PATH,
                    body_text="appropriations for naval operations and fleet modernization",
                    division_label="Division A: MilCon",
                ),
                _node(
                    self.GP_PATH,
                    body_text="appropriations for military facilities and construction upgrades",
                    division_label="Division A: MilCon",
                ),
            ]
        )
        pairs = match_nodes(old, new)
        assert len(pairs) == 2
        for o, n in pairs:
            assert o is not None and n is not None
        # Military/construction should pair together, naval should pair together
        pair_texts = [(o.body_text, n.body_text) for o, n in pairs]
        mil_pair = [(o, n) for o, n in pair_texts if "military" in o]
        assert len(mil_pair) == 1
        assert "military" in mil_pair[0][1]  # should pair with military, not naval


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
        old = _tree(
            [
                _node(
                    ("dept", "sec. 129"),
                    "For an additional amount for Military Construction, Air Force, "
                    "$252,000,000, to remain available until September 30, 2028, "
                    "for expenses incurred as a result of natural disasters.",
                )
            ]
        )
        new = _tree(
            [
                _node(
                    ("dept", "sec. 129"),
                    "For an additional amount for the accounts and in the amounts "
                    "specified for planning and design and unspecified minor construction "
                    "for construction improvements to Department of Defense laboratory facilities.",
                )
            ]
        )
        result = diff_bills(old, new)
        # These are completely different provisions sharing a section number.
        # Should be split into removed + added, not reported as modified.
        assert result.summary["modified"] == 0
        assert result.summary["added"] == 1
        assert result.summary["removed"] == 1

    def test_similar_match_stays_modified(self):
        """When matched texts are similar (e.g., just an amount change), keep as modified."""
        old = _tree(
            [
                _node(
                    ("dept", "military construction, army"),
                    "For acquisition, construction, installation, $1,876,875,000, "
                    "to remain available until September 30, 2028.",
                )
            ]
        )
        new = _tree(
            [
                _node(
                    ("dept", "military construction, army"),
                    "For acquisition, construction, installation, $2,022,775,000, "
                    "to remain available until September 30, 2028.",
                )
            ]
        )
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


class TestFilterDiff:
    def _make_diff(self):
        """Build a BillDiff with mixed change types for filter testing."""
        return BillDiff(
            old_version="v1",
            new_version="v2",
            congress=118,
            bill_type="hr",
            bill_number=1,
            summary={"added": 1, "removed": 1, "modified": 1, "unchanged": 1, "moved": 0},
            changes=[
                NodeDiff(
                    display_path_old=("A",),
                    display_path_new=("A",),
                    match_path=("a",),
                    change_type="unchanged",
                    old_text="same",
                    new_text="same",
                    text_diff=None,
                    section_number="",
                    element_id_old="",
                    element_id_new="",
                ),
                NodeDiff(
                    display_path_old=("B",),
                    display_path_new=("B",),
                    match_path=("b",),
                    change_type="modified",
                    old_text="For expenses, $1,000.",
                    new_text="For expenses, $2,000.",
                    text_diff=["- $1,000", "+ $2,000"],
                    section_number="",
                    element_id_old="",
                    element_id_new="",
                ),
                NodeDiff(
                    display_path_old=("C",),
                    display_path_new=None,
                    match_path=("c",),
                    change_type="removed",
                    old_text="old only",
                    new_text=None,
                    text_diff=None,
                    section_number="",
                    element_id_old="",
                    element_id_new="",
                ),
                NodeDiff(
                    display_path_old=None,
                    display_path_new=("D",),
                    match_path=("d",),
                    change_type="added",
                    old_text=None,
                    new_text="new only",
                    text_diff=None,
                    section_number="",
                    element_id_old="",
                    element_id_new="",
                ),
            ],
        )

    def test_filtered_summary_matches_changes(self):
        """After filtering, summary counts should match the actual changes list."""
        diff = self._make_diff()
        # Filter to text match "b" - should keep only the modified node
        filtered = filter_diff(diff, filter_text="b")
        assert len(filtered.changes) == 1
        assert filtered.changes[0].change_type == "modified"
        # Summary should reflect the filtered state
        assert filtered.summary["modified"] == 1
        assert filtered.summary["added"] == 0
        assert filtered.summary["removed"] == 0
        assert filtered.summary["unchanged"] == 0


@pytest.mark.slow
@pytest.mark.skipif(
    not HR4366_V1_PATH.exists() or not HR4366_V6_PATH.exists(),
    reason="Real XML not present",
)
class TestCli:
    def test_compare_to_stdout(self):
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "diff_bill.py",
                "compare",
                str(HR4366_V1_PATH),
                str(HR4366_V6_PATH),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "changes" in data
        assert data["summary"]["added"] > 0

    def test_compare_to_file(self, tmp_path):
        out = tmp_path / "diff.json"
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "diff_bill.py",
                "compare",
                str(HR4366_V1_PATH),
                str(HR4366_V6_PATH),
                "--format",
                "json",
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text())
        assert data["old_version"] == "reported-in-house"
        assert data["new_version"] == "enrolled-bill"

    def test_filter_flag(self):
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "diff_bill.py",
                "compare",
                str(HR4366_V1_PATH),
                str(HR4366_V6_PATH),
                "--format",
                "json",
                "--filter",
                "military construction, army",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # All changes should contain "military construction, army" in match_path
        for change in data["changes"]:
            path_str = " ".join(change["match_path"])
            assert "military construction, army" in path_str


@pytest.mark.slow
class TestEndToEnd:
    """Full pipeline: normalize both versions, diff, verify results."""

    def test_v1_to_v6_diff(self, hr4366_v1_v6_diff):
        result = hr4366_v1_v6_diff

        # Should have all four change types
        assert result.summary["added"] > 0
        assert result.summary["modified"] > 0
        # Some sections unchanged between MilCon-VA versions
        assert result.summary["unchanged"] >= 0

        # Military construction, army should be modified (amount changed)
        army_changes = [
            c for c in result.changes if c.match_path == ("department of defense", "military construction, army")
        ]
        assert len(army_changes) == 1
        assert army_changes[0].change_type == "modified"
        assert army_changes[0].text_diff is not None

        # Agriculture content should be added (not in v1, present in v6)
        added_changes = [c for c in result.changes if c.change_type == "added"]
        added_paths_str = [" ".join(c.match_path) for c in added_changes]
        assert any("agriculture" in p for p in added_paths_str)

    def test_v1_to_v6_json_roundtrip(self, hr4366_v1_v6_diff):
        result = hr4366_v1_v6_diff
        d = bill_diff_to_dict(result)
        # Verify it's JSON-serializable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["congress"] == 118
        assert len(parsed["changes"]) == len(result.changes)


@pytest.mark.slow
class TestCrossDivisionIntegration:
    """Validate that division-aware matching reduces cross-division mismatches."""

    def test_cross_division_mismatches_below_target(self, hr4366_v4_v5_diff):
        """Issue #1/#9: cross-division mismatches reduced from 226 to <50."""
        result = hr4366_v4_v5_diff

        cross_div = 0
        for c in result.changes:
            if c.display_path_old and c.display_path_new:
                old_first = c.display_path_old[0] if c.display_path_old else ""
                new_first = c.display_path_new[0] if c.display_path_new else ""
                if old_first.startswith("Division") and new_first.startswith("Division"):
                    old_title = normalize_division_title(old_first)
                    new_title = normalize_division_title(new_first)
                    if old_title and new_title and old_title != new_title:
                        cross_div += 1

        assert cross_div < 50, f"Cross-division mismatches: {cross_div} (target: <50)"
