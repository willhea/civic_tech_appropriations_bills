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


# --- B2: line-number stripping (gap-based) ------------------------------
# Real GPO layout: line-number digit at x0 ~ 126-133, body column begins
# at x0 ~ 150 -- so the gap between the digit's x1 and the next char's x0
# is consistently >= 10px. A digit-prefix inside legitimate text like
# "21st" has normal kerning (gap ~ 0-2px). The gap is the discriminator.


def test_strip_line_number_prefix_strips_single_digit_before_uppercase():
    """``7  TITLE I`` (line-number gap) -> ``TITLE I``."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("7", 133, 100),  # x1 = 139
        _char("T", 150, 100),  # gap = 11
        _char("I", 156, 100),
        _char("T", 162, 100),
        _char("L", 168, 100),
        _char("E", 174, 100),
        _char(" ", 180, 100),
        _char("I", 186, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "TITLE I"


def test_strip_line_number_prefix_strips_two_digits_glued_to_section():
    """``21  SEC. 101.`` -> ``SEC. 101.``."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("2", 126, 100),  # x1 = 132
        _char("1", 133, 100),  # x1 = 139, kerned to next digit
        _char("S", 150, 100),  # gap = 11
        _char("E", 156, 100),
        _char("C", 162, 100),
        _char(".", 168, 100),
        _char(" ", 174, 100),
        _char("1", 180, 100),
        _char("0", 186, 100),
        _char("1", 192, 100),
        _char(".", 198, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "SEC. 101."


def test_strip_line_number_prefix_strips_when_body_continues_lowercase():
    """Body lines that wrap mid-sentence start with lowercase. The gap
    discriminator catches these where the plan's regex (which required
    uppercase follower) would not."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("4", 133, 100),  # x1 = 139
        _char("e", 150, 100),  # gap = 11
        _char("r", 156, 100),
        _char("w", 162, 100),
        _char("i", 168, 100),
        _char("s", 174, 100),
        _char("e", 180, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "erwise"


def test_strip_line_number_prefix_strips_when_body_starts_with_punctuation():
    """``10(b) The limitation`` -> ``(b) The limitation``."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("1", 126, 100),
        _char("0", 133, 100),  # x1 = 139
        _char("(", 150, 100),  # gap = 11
        _char("b", 156, 100),
        _char(")", 162, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "(b)"


def test_strip_line_number_prefix_handles_be_it_enacted():
    """``1Be it enacted`` -> ``Be it enacted``."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("1", 133, 100),  # x1 = 139
        _char("B", 150, 100),  # gap = 11
        _char("e", 156, 100),
        _char(" ", 162, 100),
        _char("i", 168, 100),
        _char("t", 174, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "Be it"


def test_strip_line_number_prefix_leaves_kerned_digit_run_untouched():
    """``21st Century Cures Act``: digits kerned tight to the following
    letter (gap ~ 0px), NOT a line number."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("2", 130, 100),  # x1 = 136
        _char("1", 136, 100),  # x1 = 142, abuts next char
        _char("s", 142, 100),  # gap = 0
        _char("t", 148, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "21st"


def test_strip_line_number_prefix_leaves_no_leading_digit_untouched():
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [_char("(", 100, 100), _char("a", 106, 100), _char(")", 112, 100)]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"] == "(a)"


def test_strip_line_number_prefix_leaves_digit_with_narrow_gap_untouched():
    """A digit followed by an inter-word space (~2-3px) is body text, not
    a line number. Threshold is 5px so gap of 3 keeps the digit intact."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [
        _char("4", 133, 100),  # x1 = 139
        _char(" ", 142, 100),  # gap = 3 (narrow, intra-line space)
        _char("s", 148, 100),
    ]
    out = _strip_line_number_prefix(_finalize_line(chars))
    assert out["text"].startswith("4")


def test_strip_line_number_prefix_advances_x0_past_digit():
    """After stripping, the line's x0 reflects the first non-digit char."""
    from parsers.pdf_parser import _finalize_line, _strip_line_number_prefix

    chars = [_char("3", 133, 100), _char("S", 150, 100), _char("E", 156, 100)]
    line = _finalize_line(chars)
    assert line["x0"] == 133

    out = _strip_line_number_prefix(line)
    assert out["text"] == "SE"
    assert out["x0"] == 150


def test_strip_line_numbers_applies_to_every_line_in_a_list():
    from parsers.pdf_parser import _finalize_line, _strip_line_numbers

    line_a = _finalize_line([_char("7", 133, 100), _char("T", 150, 100), _char("I", 156, 100)])
    line_b = _finalize_line([_char("(", 100, 120), _char("a", 106, 120), _char(")", 112, 120)])
    out = _strip_line_numbers([line_a, line_b])
    assert [ln["text"] for ln in out] == ["TI", "(a)"]


# --- B3: cover-page / preamble guard ------------------------------------


def _line(text: str) -> dict:
    """Minimal Line dict for tests that only exercise text-level logic."""
    return {"text": text, "top": 0.0, "x0": 0.0, "x1": 0.0, "chars": []}


def test_split_preamble_finds_enacting_clause():
    """Standard GPO bill: cover-page lines + enacting clause + body. The
    enacting clause is the last line of the preamble; everything after
    is body."""
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("Calendar No. 456"),
        _line("H. R. 8752"),
        _line("A BILL"),
        _line("Making appropriations for the Department of Homeland Security..."),
        _line("Be it enacted by the Senate and House of Representa-"),
        _line("tives of the United States of America..."),
        _line("That the following sums..."),
        _line("TITLE I"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert len(preamble) == 5
    assert preamble[-1]["text"].startswith("Be it enacted")
    assert [ln["text"] for ln in body] == [
        "tives of the United States of America...",
        "That the following sums...",
        "TITLE I",
    ]


def test_split_preamble_is_case_insensitive():
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("Cover stuff"),
        _line("BE IT ENACTED BY THE SENATE AND HOUSE OF REPRESENTATIVES"),
        _line("Body here"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert len(preamble) == 2
    assert body[0]["text"] == "Body here"


def test_split_preamble_falls_back_to_structural_marker_for_drafts():
    """Committee prints / drafts may lack the standard enacting clause.
    Fall back to the first DIVISION/TITLE/SEC. line within the scan
    window — drop cover-page lines, keep the structural marker as the
    body's first line."""
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("DRAFT - PRE-DECISIONAL"),
        _line("Committee Print No. 47"),
        _line("Various boilerplate"),
        _line("TITLE I"),
        _line("First body line"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert [ln["text"] for ln in preamble] == [
        "DRAFT - PRE-DECISIONAL",
        "Committee Print No. 47",
        "Various boilerplate",
    ]
    assert body[0]["text"] == "TITLE I"


def test_split_preamble_fallback_recognizes_section_marker():
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("Cover line"),
        _line("SEC. 101. SHORT TITLE."),
        _line("Body"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert len(preamble) == 1
    assert body[0]["text"] == "SEC. 101. SHORT TITLE."


def test_split_preamble_fallback_recognizes_division_marker():
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("Cover"),
        _line("DIVISION A"),
        _line("Body"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert len(preamble) == 1
    assert body[0]["text"] == "DIVISION A"


def test_split_preamble_returns_all_body_when_no_marker_found():
    """Last-resort: if neither enacting clause nor structural marker is
    visible in the scan window, return the full input as body. The state
    machine's "no open leaf" logic handles the absorbed cover-page lines."""
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("Just"),
        _line("a few"),
        _line("random lines"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert preamble == []
    assert len(body) == 3


def test_split_preamble_does_not_match_enacting_clause_in_body_text():
    """Once we've passed the cover-page region, a stray mention of
    'Be it enacted' deep in the body shouldn't re-anchor the split.
    The scan stops at the first match by design — multiple matches are
    just resolved to the first."""
    from parsers.pdf_parser import _split_preamble_and_body

    lines = [
        _line("Cover"),
        _line("Be it enacted by the Senate and House of Representatives"),
        _line("Body section A"),
        _line("Be it enacted by the Senate (quoted in another bill)"),
        _line("Body section B"),
    ]
    preamble, body = _split_preamble_and_body(lines)
    assert len(preamble) == 2
    assert len(body) == 3
    assert body[0]["text"] == "Body section A"


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
