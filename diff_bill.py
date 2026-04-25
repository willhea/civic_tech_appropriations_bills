"""Compare two bill versions and produce a structured diff."""

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from bill_tree import BillNode, BillTree, normalize_division_title

# --- Financial amount extraction ---

_DOLLAR_RE = re.compile(r"\$[\d,]+")
_AMENDMENT_RE = re.compile(r"\((?:increased|reduced|decreased) by \$[\d,]+\)")


def extract_amounts(text: str) -> tuple[int, ...]:
    """Find all dollar amounts in text.

    Returns tuple of integer values in document order. Filters $0 amounts.
    Strips floor amendment annotations like (increased by $X) before scanning.
    """
    text = _AMENDMENT_RE.sub("", text)
    results = []
    for match in _DOLLAR_RE.finditer(text):
        value = int(match.group().replace("$", "").replace(",", ""))
        if value == 0:
            continue
        results.append(value)
    return tuple(results)


def _extract_word_amounts(words: list[str]) -> list[tuple[int, int]]:
    """Find dollar amounts in a word list, returning (word_index, value) pairs.

    Filters $0 amounts. Assumes amendment annotations already stripped.
    """
    results = []
    for i, word in enumerate(words):
        m = _DOLLAR_RE.search(word)
        if m:
            value = int(m.group().replace("$", "").replace(",", ""))
            if value != 0:
                results.append((i, value))
    return results


def match_amounts(
    old_text: str | None,
    new_text: str | None,
) -> list[tuple[int | None, int | None]]:
    """Pair dollar amounts across old/new text using word-level diff alignment.

    Returns list of (old_value, new_value) pairs where:
    - (old, new): matched pair (same or changed amount in same context)
    - (old, None): removed amount
    - (None, new): added amount

    Uses SequenceMatcher to align old/new words, then traces dollar amounts
    through the diff opcodes to determine pairing.
    """
    old_clean = _AMENDMENT_RE.sub("", old_text) if old_text else ""
    new_clean = _AMENDMENT_RE.sub("", new_text) if new_text else ""
    old_words = old_clean.split()
    new_words = new_clean.split()

    old_amounts = _extract_word_amounts(old_words)
    new_amounts = _extract_word_amounts(new_words)

    if not old_amounts and not new_amounts:
        return []

    # Handle one side empty (added/removed sections)
    if not old_words:
        return [(None, val) for _, val in new_amounts]
    if not new_words:
        return [(val, None) for _, val in old_amounts]

    sm = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    pairs: list[tuple[int | None, int | None]] = []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        old_in_range = [(idx, val) for idx, val in old_amounts if i1 <= idx < i2]
        new_in_range = [(idx, val) for idx, val in new_amounts if j1 <= idx < j2]

        if op == "equal":
            # Equal blocks: amounts should match 1:1
            for (_, ov), (_, nv) in zip(old_in_range, new_in_range):
                pairs.append((ov, nv))
        elif op == "delete":
            for _, ov in old_in_range:
                pairs.append((ov, None))
        elif op == "insert":
            for _, nv in new_in_range:
                pairs.append((None, nv))
        elif op == "replace":
            # Pair positionally within the replace block
            max_len = max(len(old_in_range), len(new_in_range))
            for k in range(max_len):
                ov = old_in_range[k][1] if k < len(old_in_range) else None
                nv = new_in_range[k][1] if k < len(new_in_range) else None
                pairs.append((ov, nv))

    return pairs


@dataclass(frozen=True)
class FinancialChange:
    """Financial analysis of a single NodeDiff."""

    old_amounts: tuple[int, ...]
    new_amounts: tuple[int, ...]
    amounts_changed: bool
    paired_amounts: tuple[tuple[int | None, int | None], ...]
    has_amendment_annotations: bool = False


def compute_financial_change(
    old_text: str | None,
    new_text: str | None,
) -> FinancialChange | None:
    """Compare dollar amounts between old and new text.

    Returns None if no amounts on either side (non-financial section).
    """
    has_annotations = bool(
        (old_text and _AMENDMENT_RE.search(old_text)) or (new_text and _AMENDMENT_RE.search(new_text))
    )

    old_amounts = extract_amounts(old_text) if old_text else ()
    new_amounts = extract_amounts(new_text) if new_text else ()

    if not old_amounts and not new_amounts:
        return None

    paired = match_amounts(old_text, new_text)
    return FinancialChange(
        old_amounts=old_amounts,
        new_amounts=new_amounts,
        amounts_changed=Counter(old_amounts) != Counter(new_amounts),
        paired_amounts=tuple(paired),
        has_amendment_annotations=has_annotations,
    )


def financial_change_to_dict(fc: FinancialChange) -> dict:
    """Serialize a FinancialChange for JSON output."""
    return {
        "old_amounts": list(fc.old_amounts),
        "new_amounts": list(fc.new_amounts),
        "amounts_changed": fc.amounts_changed,
        "paired_amounts": [list(pair) for pair in fc.paired_amounts],
        "has_amendment_annotations": fc.has_amendment_annotations,
    }


def _similarity_pair(
    old_nodes: list[BillNode],
    new_nodes: list[BillNode],
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Greedy best-match pairing by text similarity within a group."""
    if not old_nodes and not new_nodes:
        return []
    if not old_nodes:
        return [(None, n) for n in new_nodes]
    if not new_nodes:
        return [(o, None) for o in old_nodes]
    if len(old_nodes) == 1 and len(new_nodes) == 1:
        return [(old_nodes[0], new_nodes[0])]

    # Compute all pairwise similarities
    candidates: list[tuple[float, int, int]] = []
    for oi, o in enumerate(old_nodes):
        o_norm = _normalize_text(o.body_text)
        for ni, n in enumerate(new_nodes):
            n_norm = _normalize_text(n.body_text)
            sim = _text_similarity(o_norm, n_norm)
            candidates.append((sim, oi, ni))

    # Greedy: highest similarity first
    candidates.sort(reverse=True)
    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    pairs: list[tuple[BillNode | None, BillNode | None]] = []

    for _sim, oi, ni in candidates:
        if oi in claimed_old or ni in claimed_new:
            continue
        claimed_old.add(oi)
        claimed_new.add(ni)
        pairs.append((old_nodes[oi], new_nodes[ni]))

    # Leftovers
    for oi, o in enumerate(old_nodes):
        if oi not in claimed_old:
            pairs.append((o, None))
    for ni, n in enumerate(new_nodes):
        if ni not in claimed_new:
            pairs.append((None, n))

    return pairs


def _match_collision_group(
    old_nodes: list[BillNode],
    new_nodes: list[BillNode],
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Resolve a collision group (multiple nodes sharing one match_path).

    Uses division titles to sub-group, then text similarity as fallback.
    """
    # Step 1: Sub-group by normalized division title
    old_by_div: dict[str, list[BillNode]] = defaultdict(list)
    new_by_div: dict[str, list[BillNode]] = defaultdict(list)
    for node in old_nodes:
        old_by_div[normalize_division_title(node.division_label)].append(node)
    for node in new_nodes:
        new_by_div[normalize_division_title(node.division_label)].append(node)

    pairs: list[tuple[BillNode | None, BillNode | None]] = []
    unmatched_old: list[BillNode] = []
    unmatched_new: list[BillNode] = []

    all_divs = dict.fromkeys(list(old_by_div.keys()) + list(new_by_div.keys()))

    # Step 2: Pair within each division sub-group
    for div_title in all_divs:
        div_old = old_by_div.get(div_title, [])
        div_new = new_by_div.get(div_title, [])

        if not div_old:
            unmatched_new.extend(div_new)
        elif not div_new:
            unmatched_old.extend(div_old)
        else:
            sub_pairs = _similarity_pair(div_old, div_new)
            for o, n in sub_pairs:
                if o is None:
                    unmatched_new.append(n)
                elif n is None:
                    unmatched_old.append(o)
                else:
                    pairs.append((o, n))

    # Step 3-4: Cross-division similarity fallback for leftovers
    if unmatched_old and unmatched_new:
        cross_pairs = _similarity_pair(unmatched_old, unmatched_new)
        leftover_old = []
        leftover_new = []
        for o, n in cross_pairs:
            if o is None:
                leftover_new.append(n)
            elif n is None:
                leftover_old.append(o)
            else:
                pairs.append((o, n))
        unmatched_old = leftover_old
        unmatched_new = leftover_new

    # Step 5: True leftovers
    for o in unmatched_old:
        pairs.append((o, None))
    for n in unmatched_new:
        pairs.append((None, n))

    return pairs


def match_nodes(
    old: BillTree,
    new: BillTree,
) -> list[tuple[BillNode | None, BillNode | None]]:
    """Match nodes across two bill versions by match_path.

    Returns list of (old_node, new_node) tuples where one side may be None:
    - (old, new): matched pair
    - (old, None): removed (only in old)
    - (None, new): added (only in new)

    For unique match_paths, pairs directly (fast path). For collision groups
    (multiple nodes sharing one match_path), uses division-aware sub-grouping
    with text similarity fallback.
    """
    # Group nodes by match_path
    old_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)
    new_groups: dict[tuple[str, ...], list[BillNode]] = defaultdict(list)

    for node in old.nodes:
        old_groups[node.match_path].append(node)
    for node in new.nodes:
        new_groups[node.match_path].append(node)

    all_paths = dict.fromkeys(list(old_groups.keys()) + list(new_groups.keys()))

    pairs: list[tuple[BillNode | None, BillNode | None]] = []

    for path in all_paths:
        old_nodes = old_groups.get(path, [])
        new_nodes = new_groups.get(path, [])

        if len(old_nodes) <= 1 and len(new_nodes) <= 1:
            # Fast path: no collision, preserve current behavior
            pairs.append(
                (
                    old_nodes[0] if old_nodes else None,
                    new_nodes[0] if new_nodes else None,
                )
            )
        else:
            pairs.extend(_match_collision_group(old_nodes, new_nodes))

    return pairs


def diff_text(old_text: str, new_text: str) -> list[str]:
    """Produce unified diff lines between two text blocks.

    Returns empty list if texts are identical.
    """
    if old_text == new_text:
        return []

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="old",
            tofile="new",
            lineterm="",
        )
    )
    # Strip trailing whitespace from each line
    return [line.rstrip() for line in diff_lines]


@dataclass(frozen=True)
class NodeDiff:
    """Diff result for a single node."""

    display_path_old: tuple[str, ...] | None
    display_path_new: tuple[str, ...] | None
    match_path: tuple[str, ...]
    change_type: str  # "added" | "removed" | "modified" | "unchanged"
    old_text: str | None
    new_text: str | None
    text_diff: list[str] | None
    section_number: str
    element_id_old: str
    element_id_new: str


@dataclass(frozen=True)
class BillDiff:
    """Complete diff between two bill versions."""

    old_version: str
    new_version: str
    congress: int
    bill_type: str
    bill_number: int
    summary: dict
    changes: list[NodeDiff]


_SIMILARITY_THRESHOLD = 0.4


def _normalize_text(text: str) -> str:
    """Normalize whitespace for comparison: collapse runs, strip."""
    return " ".join(text.split())


def _text_similarity(a: str, b: str) -> float:
    """Compute word-level similarity ratio between two texts (0.0 to 1.0)."""
    return difflib.SequenceMatcher(None, a.split(), b.split()).ratio()


_MOVE_THRESHOLD = 0.6


def reconcile_moves(
    changes: list[NodeDiff],
    threshold: float = _MOVE_THRESHOLD,
) -> list[NodeDiff]:
    """Re-link removed+added pairs that are actually moved sections.

    Computes pairwise text similarity between removed and added entries.
    Pairs above threshold are greedily matched (highest similarity first)
    and converted to change_type="moved".
    """
    removed = [(i, c) for i, c in enumerate(changes) if c.change_type == "removed"]
    added = [(i, c) for i, c in enumerate(changes) if c.change_type == "added"]

    if not removed or not added:
        return changes

    # Compute all pairwise similarities
    candidates: list[tuple[float, int, int]] = []
    for ri, (_, rc) in enumerate(removed):
        old_norm = _normalize_text(rc.old_text or "")
        for ai, (_, ac) in enumerate(added):
            new_norm = _normalize_text(ac.new_text or "")
            sim = _text_similarity(old_norm, new_norm)
            if sim >= threshold:
                candidates.append((sim, ri, ai))

    if not candidates:
        return changes

    # Greedy: highest similarity first
    candidates.sort(reverse=True)
    claimed_removed: set[int] = set()
    claimed_added: set[int] = set()
    moved_indices: set[int] = set()  # original indices to remove
    moved_entries: list[NodeDiff] = []

    for sim, ri, ai in candidates:
        if ri in claimed_removed or ai in claimed_added:
            continue
        claimed_removed.add(ri)
        claimed_added.add(ai)

        orig_ri, rc = removed[ri]
        orig_ai, ac = added[ai]
        moved_indices.add(orig_ri)
        moved_indices.add(orig_ai)

        # Compute text_diff if texts differ
        old_norm = _normalize_text(rc.old_text or "")
        new_norm = _normalize_text(ac.new_text or "")
        text_changes = diff_text(old_norm, new_norm) if old_norm != new_norm else None

        moved_entries.append(
            NodeDiff(
                display_path_old=rc.display_path_old,
                display_path_new=ac.display_path_new,
                match_path=rc.match_path,
                change_type="moved",
                old_text=rc.old_text,
                new_text=ac.new_text,
                text_diff=text_changes,
                section_number=ac.section_number or rc.section_number,
                element_id_old=rc.element_id_old,
                element_id_new=ac.element_id_new,
            )
        )

    # Rebuild: keep non-moved entries in original order, append moved at end
    result = [c for i, c in enumerate(changes) if i not in moved_indices]
    result.extend(moved_entries)
    return result


def _count_changes(changes: list[NodeDiff]) -> dict:
    """Compute summary counts from the final changes list."""
    counts = Counter(c.change_type for c in changes)
    return {t: counts.get(t, 0) for t in ("added", "removed", "modified", "unchanged", "moved")}


def diff_bills(old: BillTree, new: BillTree) -> BillDiff:
    """Compare two bill versions and produce a structured diff."""
    pairs = match_nodes(old, new)
    changes: list[NodeDiff] = []

    for old_node, new_node in pairs:
        if old_node is None and new_node is not None:
            changes.append(
                NodeDiff(
                    display_path_old=None,
                    display_path_new=new_node.display_path,
                    match_path=new_node.match_path,
                    change_type="added",
                    old_text=None,
                    new_text=new_node.body_text,
                    text_diff=None,
                    section_number=new_node.section_number,
                    element_id_old="",
                    element_id_new=new_node.element_id,
                )
            )

        elif old_node is not None and new_node is None:
            changes.append(
                NodeDiff(
                    display_path_old=old_node.display_path,
                    display_path_new=None,
                    match_path=old_node.match_path,
                    change_type="removed",
                    old_text=old_node.body_text,
                    new_text=None,
                    text_diff=None,
                    section_number=old_node.section_number,
                    element_id_old=old_node.element_id,
                    element_id_new="",
                )
            )

        elif old_node is not None and new_node is not None:
            old_normalized = _normalize_text(old_node.body_text)
            new_normalized = _normalize_text(new_node.body_text)
            text_changes = diff_text(old_normalized, new_normalized)
            if not text_changes:
                changes.append(
                    NodeDiff(
                        display_path_old=old_node.display_path,
                        display_path_new=new_node.display_path,
                        match_path=old_node.match_path,
                        change_type="unchanged",
                        old_text=old_node.body_text,
                        new_text=new_node.body_text,
                        text_diff=None,
                        section_number=new_node.section_number or old_node.section_number,
                        element_id_old=old_node.element_id,
                        element_id_new=new_node.element_id,
                    )
                )
            elif _text_similarity(old_normalized, new_normalized) < _SIMILARITY_THRESHOLD:
                # Texts too different: false match (e.g., reused section number).
                changes.append(
                    NodeDiff(
                        display_path_old=old_node.display_path,
                        display_path_new=None,
                        match_path=old_node.match_path,
                        change_type="removed",
                        old_text=old_node.body_text,
                        new_text=None,
                        text_diff=None,
                        section_number=old_node.section_number,
                        element_id_old=old_node.element_id,
                        element_id_new="",
                    )
                )
                changes.append(
                    NodeDiff(
                        display_path_old=None,
                        display_path_new=new_node.display_path,
                        match_path=new_node.match_path,
                        change_type="added",
                        old_text=None,
                        new_text=new_node.body_text,
                        text_diff=None,
                        section_number=new_node.section_number,
                        element_id_old="",
                        element_id_new=new_node.element_id,
                    )
                )
            else:
                changes.append(
                    NodeDiff(
                        display_path_old=old_node.display_path,
                        display_path_new=new_node.display_path,
                        match_path=old_node.match_path,
                        change_type="modified",
                        old_text=old_node.body_text,
                        new_text=new_node.body_text,
                        text_diff=text_changes,
                        section_number=new_node.section_number or old_node.section_number,
                        element_id_old=old_node.element_id,
                        element_id_new=new_node.element_id,
                    )
                )

    changes = reconcile_moves(changes)

    return BillDiff(
        old_version=old.version,
        new_version=new.version,
        congress=old.congress,
        bill_type=old.bill_type,
        bill_number=old.bill_number,
        summary=_count_changes(changes),
        changes=changes,
    )


def bill_diff_to_dict(diff: BillDiff, *, financial: bool = False) -> dict:
    """Serialize a BillDiff to a JSON-compatible dict."""
    changes_list = []
    financial_change_count = 0

    for c in diff.changes:
        entry = {
            "display_path_old": list(c.display_path_old) if c.display_path_old else None,
            "display_path_new": list(c.display_path_new) if c.display_path_new else None,
            "match_path": list(c.match_path),
            "change_type": c.change_type,
            "old_text": c.old_text,
            "new_text": c.new_text,
            "text_diff": c.text_diff,
            "section_number": c.section_number,
            "element_id_old": c.element_id_old,
            "element_id_new": c.element_id_new,
        }
        if financial:
            fc = compute_financial_change(c.old_text, c.new_text)
            if fc is not None:
                entry["financial"] = financial_change_to_dict(fc)
                if fc.amounts_changed:
                    financial_change_count += 1
        changes_list.append(entry)

    result = {
        "old_version": diff.old_version,
        "new_version": diff.new_version,
        "congress": diff.congress,
        "bill_type": diff.bill_type,
        "bill_number": diff.bill_number,
        "summary": diff.summary,
        "changes": changes_list,
    }
    if financial:
        result["financial_summary"] = {
            "sections_with_financial_changes": financial_change_count,
        }
    return result


# --- CLI ---


def filter_diff(
    diff: BillDiff,
    *,
    include_unchanged: bool = False,
    filter_text: str | None = None,
    financial_only: bool = False,
) -> BillDiff:
    """Apply filters to a BillDiff, returning a new BillDiff with filtered changes."""
    changes = list(diff.changes)

    if not include_unchanged:
        changes = [c for c in changes if c.change_type != "unchanged"]

    if filter_text:
        filter_lower = filter_text.lower()
        changes = [c for c in changes if filter_lower in " ".join(c.match_path)]

    if financial_only:
        changes = [
            c
            for c in changes
            if (fc := compute_financial_change(c.old_text, c.new_text)) is not None and fc.amounts_changed
        ]

    return BillDiff(
        old_version=diff.old_version,
        new_version=diff.new_version,
        congress=diff.congress,
        bill_type=diff.bill_type,
        bill_number=diff.bill_number,
        summary=_count_changes(changes),
        changes=changes,
    )


def cmd_compare(args: argparse.Namespace) -> None:
    from parsers import load_bill_tree

    old_tree = load_bill_tree(Path(args.old_xml))
    new_tree = load_bill_tree(Path(args.new_xml))
    result = diff_bills(old_tree, new_tree)

    result = filter_diff(
        result,
        include_unchanged=args.include_unchanged,
        filter_text=args.filter,
        financial_only=args.financial,
    )

    fmt = getattr(args, "format", "json")
    # HTML always gets financial enrichment; JSON only when --financial is passed
    include_financial = args.financial or fmt == "html"
    diff_dict = bill_diff_to_dict(result, financial=include_financial)

    # Extract version numbers from filenames (e.g., "1_reported-in-house.xml" -> 1)
    for key, xml_arg in (("old_version_number", args.old_xml), ("new_version_number", args.new_xml)):
        stem = Path(xml_arg).stem
        prefix = stem.split("_", 1)[0]
        if prefix.isdigit():
            diff_dict[key] = int(prefix)

    if fmt == "html":
        from formatters.html import format_html

        output = format_html(diff_dict)
    else:
        output = json.dumps(diff_dict, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two bill versions (XML or PDF) and produce a structured diff.",
    )
    subparsers = parser.add_subparsers(dest="command")

    compare = subparsers.add_parser("compare", help="Compare two bill versions")
    compare.add_argument(
        "old_xml",
        metavar="old_bill",
        help="Path to older bill (.xml or .pdf)",
    )
    compare.add_argument(
        "new_xml",
        metavar="new_bill",
        help="Path to newer bill (.xml or .pdf)",
    )
    compare.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    compare.add_argument(
        "--include-unchanged",
        action="store_true",
        help="Include unchanged nodes in output",
    )
    compare.add_argument(
        "--filter",
        help="Only include nodes whose match_path contains this substring",
    )
    compare.add_argument(
        "--financial",
        action="store_true",
        help="Only show sections with financial changes; add amount details to output",
    )
    compare.add_argument(
        "--format",
        choices=["json", "html"],
        default="html",
        help="Output format (default: html)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
