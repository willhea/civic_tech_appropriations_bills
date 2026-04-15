"""Smoke test: division-aware matching on fresh bills.

Not part of pytest. Run manually to validate matching generalizes
to bills outside the development corpus.

Usage: uv run python smoke_test_matching.py
"""

from pathlib import Path

from bill_tree import normalize_bill, normalize_division_title
from diff_bill import diff_bills


FRESH_BILLS = [
    "bills/117-hr-2471",  # Consolidated Appropriations Act, 2022
    "bills/116-hr-133",   # Consolidated Appropriations Act, 2021
]


def count_cross_division_mismatches(result):
    """Count changes where old and new display_path have different division titles."""
    cross_div = 0
    for c in result.changes:
        if c.display_path_old and c.display_path_new:
            old_first = c.display_path_old[0]
            new_first = c.display_path_new[0]
            if old_first.startswith("Division") and new_first.startswith("Division"):
                old_title = normalize_division_title(old_first)
                new_title = normalize_division_title(new_first)
                if old_title and new_title and old_title != new_title:
                    cross_div += 1
    return cross_div


def main():
    for bill_dir in FRESH_BILLS:
        bill_path = Path(bill_dir)
        if not bill_path.exists():
            print(f"\n{bill_dir}: NOT FOUND, skipping")
            continue

        versions = sorted(bill_path.glob("*.xml"))
        print(f"\n{'=' * 60}")
        print(f"{bill_dir}: {len(versions)} versions")
        print(f"{'=' * 60}")

        # Parse all versions, report node counts
        trees = {}
        for v in versions:
            try:
                tree = normalize_bill(v)
                trees[v.name] = tree
                divs = sorted(set(
                    n.division_label for n in tree.nodes if n.division_label
                ))
                print(f"  {v.name}: {len(tree.nodes)} nodes, {len(divs)} divisions")
            except Exception as e:
                print(f"  {v.name}: PARSE ERROR: {e}")

        # Diff consecutive version pairs that both have nodes
        version_names = [v.name for v in versions if v.name in trees and len(trees[v.name].nodes) > 10]
        if len(version_names) < 2:
            print("  Not enough substantial versions to diff")
            continue

        print(f"\n  {'Version Pair':<55} {'Total':>6} {'X-Div':>6} {'Moved':>6}")
        print(f"  {'-'*55} {'-'*6} {'-'*6} {'-'*6}")

        for i in range(len(version_names) - 1):
            old_name = version_names[i]
            new_name = version_names[i + 1]
            old_tree = trees[old_name]
            new_tree = trees[new_name]

            try:
                result = diff_bills(old_tree, new_tree)
                cross_div = count_cross_division_mismatches(result)
                moved = result.summary.get("moved", 0)
                total = len(result.changes)
                label = f"{old_name} -> {new_name}"
                flag = " !!!" if cross_div > 50 else ""
                print(f"  {label:<55} {total:>6} {cross_div:>6} {moved:>6}{flag}")
            except Exception as e:
                print(f"  {old_name} -> {new_name}: DIFF ERROR: {e}")

    print()


if __name__ == "__main__":
    main()
