"""Cross-version diff validation tests.

These tests verify that the diff pipeline produces correct pairings, change
types, and financial diffs when run against real bill XML. All tests require
bill XML files and are marked @slow.

Test categories:
- Hard correctness assertions: things verified as correct, must not regress
- Regression baselines: current behavior documented with comments; values may
  shift as the parser improves
"""

from collections import Counter
from pathlib import Path

import pytest

from bill_tree import normalize_bill, normalize_division_title
from diff_bill import (
    _normalize_text,
    _text_similarity,
    compute_financial_change,
    diff_bills,
    extract_amounts,
)

BILLS_DIR = Path(__file__).parent / "bills"


def _changes_by_type(diff, change_type):
    return [c for c in diff.changes if c.change_type == change_type]


def _find_change(diff, match_path):
    """Find a change by its match_path tuple."""
    for c in diff.changes:
        if c.match_path == match_path:
            return c
    return None


# ---------------------------------------------------------------------------
# Class 1: Controlled diff (118-hr-4366 v1 -> v2)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestControlledDiff:
    """Golden test: small diff between reported-in-house and engrossed-in-house.

    Same bill structure, minor content changes. 172 total changes, all
    manually verified via diff output inspection.
    """

    def test_no_removed_sections(self, hr4366_v1_v2_diff):
        assert hr4366_v1_v2_diff.summary["removed"] == 0

    def test_added_sections_are_general_provisions(self, hr4366_v1_v2_diff):
        added = _changes_by_type(hr4366_v1_v2_diff, "added")
        assert len(added) == 7
        for c in added:
            assert "general provisions" in c.match_path, f"Added section not under general provisions: {c.match_path}"

    def test_milcon_army_is_modified(self, hr4366_v1_v2_diff):
        path = ("department of defense", "military construction, army")
        change = _find_change(hr4366_v1_v2_diff, path)
        assert change is not None, "MilCon Army not found in diff"
        assert change.change_type == "modified"

    def test_va_sections_modified(self, hr4366_v1_v2_diff):
        """Key VA appropriations sections should be modified, not added/removed."""
        expected_modified = [
            ("department of veterans affairs", "veterans health administration", "medical services"),
            ("department of veterans affairs", "veterans health administration", "medical community care"),
            ("department of veterans affairs", "departmental administration", "information technology systems"),
            ("department of veterans affairs", "national cemetery administration"),
        ]
        for path in expected_modified:
            change = _find_change(hr4366_v1_v2_diff, path)
            assert change is not None, f"VA section not found: {path}"
            assert change.change_type == "modified", f"Expected modified, got {change.change_type}: {path}"

    def test_moved_section(self, hr4366_v1_v2_diff):
        moved = _changes_by_type(hr4366_v1_v2_diff, "moved")
        assert len(moved) == 1
        m = moved[0]
        assert m.display_path_old is not None
        assert m.display_path_new is not None
        # sec. 418 renumbered to sec. 420
        assert "418" in m.display_path_old[-1]
        assert "420" in m.display_path_new[-1]

    def test_no_false_matches(self, hr4366_v1_v2_diff):
        """No modified section should have similarity below the split threshold."""
        for c in _changes_by_type(hr4366_v1_v2_diff, "modified"):
            sim = _text_similarity(
                _normalize_text(c.old_text or ""),
                _normalize_text(c.new_text or ""),
            )
            assert sim >= 0.4, f"False match not caught (sim={sim:.2f}): {c.match_path}"

    def test_no_dead_zone_cases(self, hr4366_v1_v2_diff):
        """In this controlled diff, all modified sections should have high similarity."""
        for c in _changes_by_type(hr4366_v1_v2_diff, "modified"):
            sim = _text_similarity(
                _normalize_text(c.old_text or ""),
                _normalize_text(c.new_text or ""),
            )
            assert sim >= 0.6, f"Unexpected dead-zone case (sim={sim:.2f}): {c.match_path}"

    def test_summary_baseline(self, hr4366_v1_v2_diff):
        """Regression baseline for summary counts.

        Current values (2026-04-15): added=7, modified=16, unchanged=148, moved=1.
        These are verified correct. Changes indicate a parser/matching regression.
        """
        s = hr4366_v1_v2_diff.summary
        assert s["added"] == 7
        assert s["removed"] == 0
        assert s["modified"] == 16
        assert s["unchanged"] == 148
        assert s["moved"] == 1

    # -- Financial validation --

    def test_financial_changes_are_annotation_only(self, hr4366_v1_v2_diff):
        """All financial changes in v1->v2 come from floor amendment annotations.

        Base dollar amounts are identical; only effective amounts (after applying
        'increased by' / 'reduced by' annotations) differ. This documents the
        amendment annotation display gap (issue #7): the report shows base amounts
        as unchanged while real appropriations shifted.
        """
        financially_changed = []
        for c in hr4366_v1_v2_diff.changes:
            if c.old_text and c.new_text:
                fc = compute_financial_change(c.old_text, c.new_text)
                if fc and fc.amounts_changed:
                    financially_changed.append((c, fc))

        assert len(financially_changed) == 7

        for change, fc in financially_changed:
            assert fc.has_amendment_annotations, f"Expected amendment annotations: {change.match_path}"
            # Base amounts are identical in every pair
            for old_val, new_val in fc.paired_amounts:
                assert old_val == new_val, (
                    f"Base amounts differ (not annotation-only): {old_val} != {new_val} in {change.match_path}"
                )

    def test_milcon_army_has_amounts_but_base_unchanged(self, hr4366_v1_v2_diff):
        """MilCon Army has dollar amounts but base amounts didn't change."""
        path = ("department of defense", "military construction, army")
        change = _find_change(hr4366_v1_v2_diff, path)
        assert change is not None

        old_amounts = extract_amounts(change.old_text or "")
        new_amounts = extract_amounts(change.new_text or "")
        assert len(old_amounts) > 0, "MilCon Army should have dollar amounts"
        assert old_amounts == new_amounts, "Base amounts should be identical"


# ---------------------------------------------------------------------------
# Class 2: Structure expansion (118-hr-4366 v1 -> v6)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestStructureExpansion:
    """Cross-structure matching: no-division bill (165 nodes) to omnibus (1095 nodes).

    v1 (reported-in-house) covers only MilCon-VA. v6 (enrolled-bill) is the
    full omnibus with Agriculture, Defense, Energy, Transportation, etc.
    """

    def test_agriculture_sections_are_added(self, hr4366_v1_v6_diff):
        """Agriculture content doesn't exist in v1, so it should all be added."""
        added = _changes_by_type(hr4366_v1_v6_diff, "added")
        ag_added = [c for c in added if "agriculture" in " ".join(c.match_path)]
        assert len(ag_added) > 0, "Agriculture sections should be added"

        # Verify none are classified as modified (would mean false match with v1 content)
        modified = _changes_by_type(hr4366_v1_v6_diff, "modified")
        ag_modified = [c for c in modified if "agriculture" in " ".join(c.match_path)]
        assert len(ag_modified) == 0, f"Agriculture sections falsely matched as modified: {len(ag_modified)}"

    def test_no_cross_department_pairing(self, hr4366_v1_v6_diff):
        """No agriculture node should be paired with a defense node (or vice versa)."""
        for c in hr4366_v1_v6_diff.changes:
            if c.display_path_old and c.display_path_new:
                old_path_str = " ".join(c.display_path_old).lower()
                new_path_str = " ".join(c.display_path_new).lower()

                ag_old = "agriculture" in old_path_str
                ag_new = "agriculture" in new_path_str
                def_old = "defense" in old_path_str
                def_new = "defense" in new_path_str

                assert not (ag_old and def_new), (
                    f"Agriculture paired with Defense: {c.display_path_old} -> {c.display_path_new}"
                )
                assert not (def_old and ag_new), (
                    f"Defense paired with Agriculture: {c.display_path_old} -> {c.display_path_new}"
                )

    def test_milcon_va_sections_matched_not_added(self, hr4366_v1_v6_diff):
        """MilCon-VA sections from v1 should be matched (modified/unchanged), not added."""
        milcon_paths = [
            ("department of defense", "military construction, army"),
            ("department of veterans affairs", "veterans health administration", "medical services"),
            ("department of veterans affairs", "national cemetery administration"),
        ]
        for path in milcon_paths:
            change = _find_change(hr4366_v1_v6_diff, path)
            assert change is not None, f"MilCon-VA section not found: {path}"
            assert change.change_type in ("modified", "unchanged"), (
                f"Expected matched, got {change.change_type}: {path}"
            )

    def test_no_split_then_readd_same_path(self, hr4366_v1_v6_diff):
        """No match_path should appear as both removed and added (matching failure)."""
        removed_paths = {c.match_path for c in _changes_by_type(hr4366_v1_v6_diff, "removed")}
        added_paths = {c.match_path for c in _changes_by_type(hr4366_v1_v6_diff, "added")}
        overlap = removed_paths & added_paths
        # Overlap is expected: section numbers like "sec. 131" are reused across
        # divisions in omnibus bills. When v1 has no divisions but v6 does, the
        # same match_path can legitimately appear in multiple collision groups.
        # Current: 9 overlapping paths. Should not grow significantly.
        assert len(overlap) <= 15, (
            f"Too many removed+added with same path ({len(overlap)}): "
            f"likely matching failure. Paths: {list(overlap)[:5]}"
        )

    def test_summary_baseline(self, hr4366_v1_v6_diff):
        """Regression baseline with tolerances.

        Current values (2026-04-15): added=943, removed=13, modified=38,
        unchanged=78, moved=36. Using directional assertions since parser
        improvements may shift counts.
        """
        s = hr4366_v1_v6_diff.summary
        assert s["added"] >= 900
        assert s["modified"] >= 30
        assert s["moved"] >= 20
        # Total changes should be close to the enrolled bill's node count
        total = sum(s.values())
        assert total >= 1000

    def test_dead_zone_count(self, hr4366_v1_v6_diff):
        """Baseline: how many modified sections have low similarity.

        Current: 1 case (administrative provisions, sim=0.43). Track to detect
        regressions or improvements when thresholds are tuned.
        """
        dead_zone = []
        for c in _changes_by_type(hr4366_v1_v6_diff, "modified"):
            sim = _text_similarity(
                _normalize_text(c.old_text or ""),
                _normalize_text(c.new_text or ""),
            )
            if sim < 0.6:
                dead_zone.append((sim, c.match_path))

        # Should not grow; currently 1
        assert len(dead_zone) <= 3, f"Dead-zone cases increased: {len(dead_zone)}. Paths: {[p for _, p in dead_zone]}"


# ---------------------------------------------------------------------------
# Class 3: Dead zone baseline (115-hr-5895 v4 -> v5)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestDeadZoneBaseline:
    """Documents the 0.4-0.6 similarity gap with real examples.

    115-hr-5895 (Energy & Water / Legislative Branch / MilCon-VA, FY2019)
    v4 (engrossed-amendment-senate) -> v5 (enrolled-bill) has the most
    dead-zone cases in the corpus: 5 sections with similarity 0.44-0.56.

    This test class exists to catch regressions and track improvement when
    thresholds are tuned.
    """

    def test_dead_zone_sections_documented(self, hr5895_v4_v5_diff):
        """Document sections in the 0.4-0.6 dead zone.

        These are classified as "modified" but have low text similarity,
        meaning they might be better classified as removed+added or as moved
        after threshold tuning. Current count: 5.
        """
        dead_zone = []
        for c in _changes_by_type(hr5895_v4_v5_diff, "modified"):
            sim = _text_similarity(
                _normalize_text(c.old_text or ""),
                _normalize_text(c.new_text or ""),
            )
            if 0.4 <= sim < 0.6:
                dead_zone.append((sim, c.match_path))

        # Baseline: 5 cases. Allow range for parser improvements.
        assert 3 <= len(dead_zone) <= 8, (
            f"Dead-zone count shifted unexpectedly: {len(dead_zone)} (baseline: 5). Paths: {[p for _, p in dead_zone]}"
        )

    def test_move_threshold_respected(self, hr5895_v4_v5_diff):
        """All moved sections must have text similarity >= the move threshold (0.6)."""
        for c in _changes_by_type(hr5895_v4_v5_diff, "moved"):
            if c.old_text and c.new_text:
                sim = _text_similarity(
                    _normalize_text(c.old_text),
                    _normalize_text(c.new_text),
                )
                assert sim >= 0.6, f"Moved section below threshold (sim={sim:.2f}): {c.match_path}"

    def test_move_detection_baseline(self, hr5895_v4_v5_diff):
        """Regression baseline for move detection.

        Current: 26 moved sections, all verified correct (including cross-
        department moves like MilCon general provisions -> Energy & Water).
        """
        moved = _changes_by_type(hr5895_v4_v5_diff, "moved")
        assert len(moved) >= 20, f"Move detection regressed: only {len(moved)} moved (baseline: 26)"

    def test_cross_division_mismatches(self, hr5895_v4_v5_diff):
        """Baseline for cross-division mismatches using normalized titles.

        Current: 51. This is a multi-division omnibus where some sections
        move between divisions during reconciliation.
        """
        cross_div = 0
        for c in hr5895_v4_v5_diff.changes:
            if c.display_path_old and c.display_path_new:
                old_first = c.display_path_old[0]
                new_first = c.display_path_new[0]
                if old_first.startswith("Division") and new_first.startswith("Division"):
                    old_title = normalize_division_title(old_first)
                    new_title = normalize_division_title(new_first)
                    if old_title and new_title and old_title != new_title:
                        cross_div += 1

        # Baseline: 51. Should decrease with matching improvements.
        assert cross_div <= 75, f"Cross-division mismatches increased: {cross_div} (baseline: 51)"

    def test_summary_baseline(self, hr5895_v4_v5_diff):
        """Regression baseline.

        Current (2026-04-15): added=29, removed=130, modified=82,
        unchanged=108, moved=26.
        """
        s = hr5895_v4_v5_diff.summary
        total = sum(s.values())
        assert total >= 300, f"Total changes dropped: {total} (baseline: 375)"
        assert s["modified"] >= 50, f"Modified count dropped: {s['modified']}"


# ---------------------------------------------------------------------------
# Corpus-wide smoke test: diff all adjacent version pairs
# ---------------------------------------------------------------------------


def _adjacent_version_pairs():
    """Discover all adjacent version pairs across the bill corpus."""
    pairs = []
    for bill_dir in sorted(BILLS_DIR.iterdir()):
        if not bill_dir.is_dir():
            continue
        versions = sorted(bill_dir.glob("*.xml"))
        for i in range(len(versions) - 1):
            old, new = versions[i], versions[i + 1]
            label = f"{bill_dir.name}/{old.stem}->{new.stem}"
            pairs.append(pytest.param(old, new, id=label))
    return pairs


# Known duplicate modified/moved entries caused by cross-division collision
# groups in omnibus bills. Duplicate "unchanged" entries are common and harmless
# (same section name in multiple divisions, all unchanged). Only modified/moved
# duplicates indicate real matching bugs.
_KNOWN_MODIFIED_MOVED_DUPLICATES = {
    # 114-hr-2029 v6->v7: general provisions sec. 514 in multiple divisions
    ("114-hr-2029", "6", "7"): 1,
    # 118-hr-4366 v4->v5: transportation/HUD collision group duplicates
    ("118-hr-4366", "4", "5"): 4,
}


def _known_duplicate_count(old_path, new_path):
    """Look up expected duplicate count for a version pair."""
    bill_name = old_path.parent.name
    old_idx = old_path.name.split("_")[0]
    new_idx = new_path.name.split("_")[0]
    return _KNOWN_MODIFIED_MOVED_DUPLICATES.get((bill_name, old_idx, new_idx), 0)


@pytest.mark.slow
@pytest.mark.parametrize("old_path,new_path", _adjacent_version_pairs())
class TestCorpusDiffSmoke:
    """Smoke tests run against every adjacent version pair in the corpus.

    These check invariants that should hold for ANY diff, without needing
    hand-curated assertions per bill.
    """

    def test_no_crash(self, old_path, new_path):
        """Diff pipeline should not crash on any version pair."""
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        result = diff_bills(old_tree, new_tree)
        assert result is not None
        assert len(result.changes) > 0

    def test_no_false_matches(self, old_path, new_path):
        """No modified section should have similarity below the split threshold (0.4)."""
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        result = diff_bills(old_tree, new_tree)

        for c in result.changes:
            if c.change_type == "modified" and c.old_text and c.new_text:
                sim = _text_similarity(
                    _normalize_text(c.old_text),
                    _normalize_text(c.new_text),
                )
                assert sim >= 0.4, f"False match leaked through (sim={sim:.2f}): {c.match_path}"

    def test_no_unexpected_duplicate_changes(self, old_path, new_path):
        """Same (match_path, change_type) should not appear twice for modified/moved.

        Duplicate "unchanged" entries are expected in omnibus bills (same section
        name in multiple divisions). But duplicate modified/moved entries indicate
        collision group bugs. Known cases tracked in _KNOWN_MODIFIED_MOVED_DUPLICATES.
        """
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        result = diff_bills(old_tree, new_tree)

        counts = Counter(
            (c.match_path, c.change_type) for c in result.changes if c.change_type in ("modified", "moved")
        )
        duplicates = {k: v for k, v in counts.items() if v > 1}
        expected = _known_duplicate_count(old_path, new_path)

        assert len(duplicates) <= expected, (
            f"Unexpected duplicate modified/moved ({len(duplicates)}, expected <={expected}): {list(duplicates.keys())}"
        )

    def test_summary_counts_non_negative(self, old_path, new_path):
        """All summary counts should be non-negative."""
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        result = diff_bills(old_tree, new_tree)

        for key, value in result.summary.items():
            assert value >= 0, f"Negative summary count {key}={value}"
