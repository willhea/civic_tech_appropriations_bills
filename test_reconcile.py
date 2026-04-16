"""Tests for section renumbering reconciliation."""

import pytest

from conftest import make_node_diff as _node
from diff_bill import reconcile_moves


class TestReconcileMoves:
    def test_identical_text_becomes_moved(self):
        text_a = "For acquisition and construction, $2,022,775,000, to remain available."
        text_b = "None of the funds shall be used for lobbying activities."

        changes = [
            _node("removed", old_path=("sec. 2",), old_text=text_a),
            _node("removed", old_path=("sec. 3",), old_text=text_b),
            _node("added", new_path=("title ii", "sec. 3"), new_text=text_a),
            _node("added", new_path=("title ii", "sec. 4"), new_text=text_b),
        ]

        result = reconcile_moves(changes)

        moved = [c for c in result if c.change_type == "moved"]
        removed = [c for c in result if c.change_type == "removed"]
        added = [c for c in result if c.change_type == "added"]

        assert len(moved) == 2
        assert len(removed) == 0
        assert len(added) == 0

        # Check first moved entry has correct paths and text
        m = next(c for c in moved if c.old_text == text_a)
        assert m.display_path_old == ("sec. 2",)
        assert m.display_path_new == ("title ii", "sec. 3")
        assert m.new_text == text_a
        assert m.text_diff is None  # identical text

    def test_below_threshold_unchanged(self):
        changes = [
            _node("removed", old_path=("sec. 1",), old_text="Short title of the act."),
            _node("added", new_path=("sec. 1",), new_text="Completely different content about sanctions and enforcement."),
        ]

        result = reconcile_moves(changes)

        assert len(result) == 2
        assert result[0].change_type == "removed"
        assert result[1].change_type == "added"

    def test_dead_zone_pair_becomes_moved(self):
        """Pairs with ~0.67 similarity (in the old 0.4-0.7 dead zone) should now reconcile as moved."""
        old_text = "For the Maritime Administration, including necessary expenses for ship disposal and related maritime operations and maintenance, $287,000,000, to remain available until expended."
        # Modified version: ~0.67 similarity (below old 0.7 threshold, above new 0.6)
        new_text = "For the Maritime Administration, including necessary expenses for ship disposal, environmental remediation, and related maritime operations, $312,000,000, to remain available."

        changes = [
            _node("removed", old_path=("maritime administration",), old_text=old_text),
            _node("added", new_path=("maritime administration", "ship disposal"), new_text=new_text),
        ]

        result = reconcile_moves(changes)

        moved = [c for c in result if c.change_type == "moved"]
        assert len(moved) == 1
        assert moved[0].text_diff is not None

    def test_low_similarity_stays_separate(self):
        """Pairs below the threshold should not be reconciled as moved."""
        changes = [
            _node("removed", old_path=("sec. 501",), old_text="Counting Veterans Cancer Act provisions for data collection."),
            _node("added", new_path=("sec. 201",), new_text="Amending Compacts of Free Association with Pacific Island nations."),
        ]

        result = reconcile_moves(changes)

        assert len(result) == 2
        assert result[0].change_type == "removed"
        assert result[1].change_type == "added"

    def test_moved_with_text_changes(self):
        old_text = "For acquisition and construction, $1,876,875,000, to remain available until September 30, 2025."
        new_text = "For acquisition and construction, $2,022,775,000, to remain available until expended."

        changes = [
            _node("removed", old_path=("sec. 5",), old_text=old_text),
            _node("added", new_path=("title ii", "sec. 10"), new_text=new_text),
        ]

        result = reconcile_moves(changes)

        assert len(result) == 1
        m = result[0]
        assert m.change_type == "moved"
        assert m.display_path_old == ("sec. 5",)
        assert m.display_path_new == ("title ii", "sec. 10")
        assert m.text_diff is not None
        assert len(m.text_diff) > 0

    def test_greedy_best_pairs_first(self):
        """Three removed, two added. Best similarity pairs claimed, leftover stays removed."""
        text_a = "For military construction of army facilities, $2,022,775,000, to remain available."
        text_b = "For naval operations and maintenance, $5,531,369,000, to remain available."
        text_c = "Short title and enactment clause for this act."

        changes = [
            _node("removed", old_path=("sec. 1",), old_text=text_a),
            _node("removed", old_path=("sec. 2",), old_text=text_b),
            _node("removed", old_path=("sec. 3",), old_text=text_c),
            _node("added", new_path=("title i", "sec. 101"), new_text=text_a),
            _node("added", new_path=("title i", "sec. 102"), new_text=text_b),
        ]

        result = reconcile_moves(changes)

        moved = [c for c in result if c.change_type == "moved"]
        removed = [c for c in result if c.change_type == "removed"]

        assert len(moved) == 2
        assert len(removed) == 1
        assert removed[0].display_path_old == ("sec. 3",)  # text_c had no match


@pytest.mark.slow
class TestReconcileIntegration:
    HR2882_V4 = "bills/118-hr-2882/4_engrossed-amendment-senate.xml"
    HR2882_V5 = "bills/118-hr-2882/5_engrossed-amendment-house.xml"

    @staticmethod
    def _skip_if_missing(*paths):
        import os
        for p in paths:
            if not os.path.exists(p):
                import pytest
                pytest.skip(f"Test XML not found: {p}")

    def test_udall_sections_moved(self):
        from pathlib import Path
        from bill_tree import normalize_bill
        from diff_bill import diff_bills

        self._skip_if_missing(self.HR2882_V4, self.HR2882_V5)

        old = normalize_bill(Path(self.HR2882_V4))
        new = normalize_bill(Path(self.HR2882_V5))
        result = diff_bills(old, new)

        moved = [c for c in result.changes if c.change_type == "moved"]
        assert len(moved) >= 3  # sec. 2, 3, 4 should be moved (sec. 1 may differ)
        assert result.summary["moved"] >= 3

        # Verify one of the moved sections has the right old/new paths
        sec2 = [c for c in moved if c.display_path_old == ("Sec. 2",)]
        if sec2:
            m = sec2[0]
            assert m.display_path_new is not None
            assert "sec." in " ".join(m.display_path_new).lower()
