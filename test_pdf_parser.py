"""Tests for the PDF backend of ``parsers.load_bill_tree``.

The smoke test below uses a committed single-page fixture and is
EXPECTED RED until Phase B1 lands a working extractor and registers
it with the parsers dispatcher. After B1 lands the test flips green
and stays green for the rest of the rebuild.

Phase B0-B8 will add more tests here as each extraction capability
lands.
"""

from __future__ import annotations

from pathlib import Path

from parsers import load_bill_tree

FIXTURE = Path(__file__).parent / "test_data" / "pdf" / "118hr8752-page5.pdf"


def _char(
    text: str,
    x0: float,
    top: float,
    *,
    size: float = 12.0,
    fontname: str = "Times-Roman",
) -> dict:
    """Build a synthetic pdfplumber-shaped char dict."""
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + size * 0.5,
        "top": top,
        "bottom": top + size,
        "size": size,
        "fontname": fontname,
    }


def test_committed_fixture_yields_at_least_one_bill_node():
    """Single-page GPO PDF must produce at least one ``BillNode``.

    The fixture is page 5 of ``bills/118-hr-8752/1_reported-in-house.pdf``
    — contains real section content (``SEC. 102.`` and following body
    text) so a working parser should recover at least one node.
    """
    assert FIXTURE.exists(), f"Committed fixture missing: {FIXTURE}"
    tree = load_bill_tree(FIXTURE)
    assert len(tree.nodes) > 0


def test_extract_pages_is_deterministic_across_calls():
    """Two calls to ``_extract_pages`` on the same PDF return equal output.

    Sorting raw chars by ``(round(top, 1), round(x0, 1), text)`` defeats
    pdfminer.six iteration-order differences so synthetic IDs and
    match_paths produced by later phases are stable. As B1+ adds nodes,
    this determinism propagates up into the ``BillTree``.
    """
    from parsers.pdf_parser import _extract_pages

    pages_a, heights_a = _extract_pages(FIXTURE)
    pages_b, heights_b = _extract_pages(FIXTURE)
    assert heights_a == heights_b
    assert pages_a == pages_b


def test_metadata_from_path_parses_corpus_layout():
    """``bills/<congress>-<type>-<number>/<idx>_<slug>.pdf`` decomposes
    into the expected metadata tuple."""
    from pathlib import Path

    from parsers.pdf_parser import _metadata_from_path

    p = Path("bills/118-hr-8752/1_reported-in-house.pdf")
    assert _metadata_from_path(p) == (118, "hr", 8752, "reported-in-house")


def test_metadata_from_path_returns_empty_for_unrecognized_layout():
    from pathlib import Path

    from parsers.pdf_parser import _metadata_from_path

    p = Path("/tmp/some-arbitrary.pdf")
    assert _metadata_from_path(p) == (0, "", 0, "")


# --- B1: font-size-aware line reconstruction -----------------------------


def test_group_into_lines_collapses_chars_at_same_top():
    from parsers.pdf_parser import _group_into_lines

    chars = [_char("H", 100, 100), _char("i", 110, 100)]
    lines = _group_into_lines(chars)
    assert len(lines) == 1
    assert lines[0]["text"] == "Hi"


def test_group_into_lines_separates_distinct_baselines():
    from parsers.pdf_parser import _group_into_lines

    chars = [_char("a", 100, 100), _char("b", 100, 130)]
    lines = _group_into_lines(chars)
    assert len(lines) == 2


def test_group_into_lines_dynamic_tolerance_bridges_small_caps_baseline_gap():
    """The signature GPO ``SEC.`` rendering: 14pt ``S`` at top=125.9
    paired with 10.54pt ``E``/``C`` at top=128.6. The chars share a
    visual baseline (bottom ~= 139.9 for both) but their ``top`` differs
    by 2.7px because the smaller-size chars have a smaller bounding box.
    Dynamic tolerance ``0.4 * 14 = 5.6px`` bridges the gap so the chars
    land on one logical line.
    """
    from parsers.pdf_parser import _group_into_lines

    chars = [
        _char("S", 178.0, 125.9, size=14.0),
        _char("E", 186.1, 128.6, size=10.54),
        _char("C", 193.9, 128.6, size=10.54),
        _char(".", 201.0, 125.9, size=14.0),
    ]
    lines = _group_into_lines(chars)
    assert len(lines) == 1
    assert lines[0]["text"] == "SEC."


def test_group_into_lines_does_not_bridge_distinct_typographic_lines():
    """A 14pt heading and a 10pt italic comment one printed line below
    sit ~14-16px apart. Dynamic tolerance for a 14pt char is 5.6px, well
    below the line gap, so they stay separate."""
    from parsers.pdf_parser import _group_into_lines

    chars = [
        _char("HEADING", 100, 100, size=14.0),
        _char("note", 100, 116, size=10.0, fontname="Times-Italic"),
    ]
    lines = _group_into_lines(chars)
    assert len(lines) == 2


def test_reattach_small_caps_merges_oversize_baseline_gap():
    """When the baseline gap exceeds dynamic tolerance, the reattach
    pass merges a small-caps continuation line into its lead-cap parent.
    Pattern: line N ends with a single isolated capital at a larger
    size; line N+1 starts at x0 ~ line N's x1 with all-upper chars at
    <= 80% of the lead size."""
    from parsers.pdf_parser import _group_into_lines, _reattach_small_caps

    chars = [
        # Line N: lead `S` at 18pt, top=100. x1 = 100 + 9 = 109.
        _char("S", 100, 100, size=18.0),
        # Line N+1: small-caps `ECRETARY` at top=115 (15px gap, > 7.2px tol).
        # x0=110 sits within +/- 5 of prev x1=109.
        _char("E", 110, 115, size=10.0),
        _char("C", 117, 115, size=10.0),
        _char("R", 124, 115, size=10.0),
        _char("E", 131, 115, size=10.0),
        _char("T", 138, 115, size=10.0),
        _char("A", 145, 115, size=10.0),
        _char("R", 152, 115, size=10.0),
        _char("Y", 159, 115, size=10.0),
    ]
    lines = _reattach_small_caps(_group_into_lines(chars))
    assert len(lines) == 1
    assert lines[0]["text"] == "SECRETARY"


def test_reattach_small_caps_does_not_merge_when_x0_far_from_prev_x1():
    """A wrapped body line that happens to be all uppercase but starts
    at the body column (not at the heading's x1) is NOT merged."""
    from parsers.pdf_parser import _group_into_lines, _reattach_small_caps

    chars = [
        # Heading "TI" at 18pt, ends near x1=119
        _char("T", 100, 100, size=18.0),
        _char("I", 110, 100, size=18.0),
        # Body "DE" at 12pt, starts at x0=100 (heading column, not x1=119)
        _char("D", 100, 120, size=12.0),
        _char("E", 110, 120, size=12.0),
    ]
    lines = _reattach_small_caps(_group_into_lines(chars))
    assert len(lines) == 2


def test_reattach_small_caps_does_not_merge_when_size_ratio_does_not_match():
    """Two lines at the same font size should never trigger the small-caps
    splice — the size ratio is the discriminator."""
    from parsers.pdf_parser import _group_into_lines, _reattach_small_caps

    chars = [
        # End-of-line single capital "F" at size 12 (e.g., end of "OF")
        _char("F", 100, 100, size=12.0),
        # Next line, x0 close to prev x1, all upper, but SAME size 12
        _char("X", 108, 115, size=12.0),
        _char("Y", 116, 115, size=12.0),
    ]
    lines = _reattach_small_caps(_group_into_lines(chars))
    assert len(lines) == 2


def test_reattach_small_caps_does_not_chain_when_merged_lead_is_small():
    """Two physically-printed lines with small-caps each — separate
    headings, not a cascade. After the first merge, the merged line's
    last char is a small-cap (size 10), which fails the
    'lead-larger-than-nxt' check, so the second small-caps run stays
    on its own line."""
    from parsers.pdf_parser import _group_into_lines, _reattach_small_caps

    chars = [
        # First heading: "SEC" via small-caps splice
        _char("S", 100, 100, size=18.0),
        _char("E", 110, 115, size=10.0),
        _char("C", 117, 115, size=10.0),
        # Second heading: "RE" at small-caps size, well below first heading
        _char("R", 100, 200, size=10.0),
        _char("E", 107, 200, size=10.0),
    ]
    lines = _reattach_small_caps(_group_into_lines(chars))
    assert len(lines) == 2
    assert lines[0]["text"] == "SEC"
    assert lines[1]["text"] == "RE"
