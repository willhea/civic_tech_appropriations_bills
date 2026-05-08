"""Tests for formatters.text_serializer.serialize_tree.

The serializer flattens a BillTree's normalized node list into readable
plaintext. New display_path segments become headings (one per line, with
blank-line separation); body_text follows. Used to populate the canonical
JSON's optional `full_text` field for full-document tracked-changes views.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bill_tree import BillNode, BillTree, normalize_bill
from formatters.text_serializer import serialize_tree


def _node(*, path: tuple[str, ...] = (), header: str = "", body: str = "", tag: str = "section") -> BillNode:
    return BillNode(
        match_path=tuple(p.lower() for p in path),
        display_path=path,
        tag=tag,
        element_id="",
        header_text=header,
        body_text=body,
        section_number="",
        division_label="",
    )


def _tree(nodes: list[BillNode]) -> BillTree:
    return BillTree(congress=118, bill_type="hr", bill_number=1, version="reported", nodes=nodes)


def test_empty_tree_serializes_to_empty_string():
    assert serialize_tree(_tree([])) == ""


def test_single_node_emits_header_and_body():
    tree = _tree([_node(path=("TITLE I", "Sec. 101"), header="Sec. 101", body="For necessary expenses, $5,000,000.")])
    out = serialize_tree(tree)
    assert "TITLE I" in out
    assert "Sec. 101" in out
    assert "For necessary expenses, $5,000,000." in out


def test_new_path_segments_become_headings_only_once():
    """Two sibling sections under the same TITLE share the parent heading,
    so the serializer should emit 'TITLE I' once, not twice."""
    nodes = [
        _node(path=("TITLE I", "Sec. 101"), body="body 101"),
        _node(path=("TITLE I", "Sec. 102"), body="body 102"),
    ]
    out = serialize_tree(_tree(nodes))
    assert out.count("TITLE I") == 1
    assert "Sec. 101" in out
    assert "Sec. 102" in out
    assert "body 101" in out
    assert "body 102" in out


def test_path_change_emits_new_segments():
    nodes = [
        _node(path=("TITLE I", "Sec. 101"), body="a"),
        _node(path=("TITLE II", "Sec. 201"), body="b"),
    ]
    out = serialize_tree(_tree(nodes))
    assert "TITLE I" in out
    assert "TITLE II" in out
    assert out.index("TITLE I") < out.index("TITLE II")


def test_node_with_empty_path_emits_only_body():
    """Some nodes (like the enacting clause) have no display_path. Emit body
    text without a heading."""
    out = serialize_tree(_tree([_node(path=(), header="", body="Be it enacted by the Senate and House…")]))
    assert "Be it enacted" in out


def test_node_with_empty_path_but_header_emits_header():
    out = serialize_tree(_tree([_node(path=(), header="ENACTING CLAUSE", body="...")]))
    assert "ENACTING CLAUSE" in out


def test_headings_are_separated_by_blank_lines():
    out = serialize_tree(
        _tree(
            [
                _node(path=("TITLE I", "Sec. 101"), body="alpha"),
                _node(path=("TITLE I", "Sec. 102"), body="beta"),
            ]
        )
    )
    # alpha and beta should each be on their own paragraph with at least one blank line between them.
    assert "alpha\n\nSec. 102" in out or "alpha\n\n" in out and "beta" in out


def test_section_node_emits_uppercased_run_in_heading():
    """Section nodes get a `SEC. N.  ` run-in heading (bill convention),
    using the section_number from the node. The redundant trailing path
    segment (lowercased "sec. 101") is suppressed so it doesn't appear
    twice."""
    nodes = [
        _node(
            path=("DEPARTMENT OF DEFENSE", "Administrative provisions", "sec. 101"),
            body="None of the funds made available...",
            tag="section",
        )
    ]
    nodes[0] = BillNode(
        match_path=("department of defense", "administrative provisions", "sec. 101"),
        display_path=("DEPARTMENT OF DEFENSE", "Administrative provisions", "sec. 101"),
        tag="section",
        element_id="",
        header_text="",
        body_text="None of the funds made available...",
        section_number="Sec. 101",
        division_label="",
    )
    out = serialize_tree(_tree(nodes))
    assert "SEC. 101." in out
    # The lowercased redundant path segment must not appear.
    assert "sec. 101" not in out
    # Body follows the run-in heading on the same line.
    assert "SEC. 101.  None of the funds" in out


@pytest.mark.slow
def test_real_bill_serializes_without_error_and_contains_known_text():
    """Smoke test: the HR4366 reported XML has 165 nodes; the serializer
    must produce non-trivial output containing recognizable strings.

    Marked `slow` because it depends on the real bill corpus, which CI
    doesn't check out (matches the pattern documented in pyproject.toml).
    """
    tree = normalize_bill(Path("bills/118-hr-4366/1_reported-in-house.xml"))
    out = serialize_tree(tree)
    assert len(out) > 1000
    assert "DEPARTMENT OF DEFENSE" in out
    assert "military construction" in out.lower()
