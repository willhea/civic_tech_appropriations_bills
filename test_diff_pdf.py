"""Unit tests for diff_pdf — block-level PDF diff with anchor labeling."""

from __future__ import annotations

from diff_pdf import _Block, _block_key, _IndexedLine, diff_pdfs
from parsers.pdf_anchors import Anchor
from parsers.pdf_text import Line, Page


def _page(page_number: int, *lines: tuple[int | None, str]) -> Page:
    return Page(page_number, tuple(Line(ln, txt) for ln, txt in lines))


def _block(anchor: Anchor | None, *lines: tuple[int, int, str]) -> _Block:
    """Build a test _Block from (page_number, line_number, text) tuples."""
    return _Block(anchor, tuple(_IndexedLine(text, p, ln) for p, ln, text in lines))


class TestBlockKey:
    def test_anchor_text_and_body_preview_combined(self):
        anchor = Anchor(2, 1, "section", "SEC. 101")
        block = _block(anchor, (2, 1, "SEC. 101. alpha body"), (2, 2, "more body"))
        assert _block_key(block) == "SEC. 101::SEC. 101. alpha body\nmore body"

    def test_preamble_block_uses_sentinel_anchor_text(self):
        block = _block(None, (1, 1, "Be it enacted by the Senate"))
        assert _block_key(block) == "(preamble)::Be it enacted by the Senate"

    def test_body_preview_capped_at_80_chars(self):
        # Two blocks with same anchor and identical first 80 chars but different
        # tails get the same key — so SequenceMatcher aligns them as 'equal'
        # and the downstream text-equality check catches the body difference.
        long_prefix = "a" * 80
        anchor = Anchor(1, 1, "section", "SEC. 1")
        block_a = _block(anchor, (1, 1, long_prefix + "X"))
        block_b = _block(anchor, (1, 1, long_prefix + "Y"))
        assert _block_key(block_a) == _block_key(block_b)


class TestNoChanges:
    def test_identical_single_page(self):
        v1 = [_page(1, (1, "SEC. 101. alpha"), (2, "beta body"))]
        v2 = [_page(1, (1, "SEC. 101. alpha"), (2, "beta body"))]
        assert diff_pdfs(v1, v2).hunks == ()


class TestAddedSection:
    def test_new_section_in_v2_emits_added_hunk(self):
        # v2 adds an entire SEC. 102 block; v1 has SEC. 101 only.
        v1 = [_page(1, (1, "SEC. 101. alpha body"), (2, "more body"))]
        v2 = [
            _page(1, (1, "SEC. 101. alpha body"), (2, "more body"), (3, "SEC. 102. new section"), (4, "new body")),
        ]
        hunks = diff_pdfs(v1, v2).hunks
        added = [h for h in hunks if h.change_type == "added"]
        assert len(added) == 1
        assert added[0].v2_anchor and added[0].v2_anchor.text == "SEC. 102"
        assert "new section" in added[0].v2_text


class TestRemovedSection:
    def test_dropped_section_in_v1_emits_removed_hunk(self):
        v1 = [
            _page(1, (1, "SEC. 101. alpha body"), (2, "more body"), (3, "SEC. 102. obsolete"), (4, "drop me")),
        ]
        v2 = [_page(1, (1, "SEC. 101. alpha body"), (2, "more body"))]
        hunks = diff_pdfs(v1, v2).hunks
        removed = [h for h in hunks if h.change_type == "removed"]
        assert len(removed) == 1
        assert removed[0].v1_anchor and removed[0].v1_anchor.text == "SEC. 102"


class TestModifiedSection:
    def test_body_change_within_section_emits_modified_hunk(self):
        v1 = [_page(1, (1, "SEC. 101. body original"), (2, "the program shall be operated"))]
        v2 = [_page(1, (1, "SEC. 101. body original"), (2, "the program may be operated"))]
        hunks = diff_pdfs(v1, v2).hunks
        assert len(hunks) == 1
        h = hunks[0]
        assert h.change_type == "modified"
        assert "shall" in h.v1_text and "may" in h.v2_text


class TestPageLineCitations:
    def test_anchor_block_range_covers_anchor_through_last_body_line(self):
        v1 = [_page(2, (14, "SEC. 101. some heading"), (15, "first body line"), (16, "second body line"))]
        v2 = [_page(2, (14, "SEC. 101. some heading"), (15, "EDITED first body line"), (16, "second body line"))]
        h = diff_pdfs(v1, v2).hunks[0]
        # Block range = anchor's line through the last line of its block.
        assert h.v1_range == (2, 14, 2, 16)
        assert h.v2_range == (2, 14, 2, 16)

    def test_block_can_span_pages(self):
        v1 = [
            _page(2, (24, "SEC. 101. heading"), (25, "old body")),
            _page(3, (1, "tail line")),
        ]
        v2 = [
            _page(2, (24, "SEC. 101. heading"), (25, "new body")),
            _page(3, (1, "tail line")),
        ]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.v1_range == (2, 24, 3, 1)
        assert h.v2_range == (2, 24, 3, 1)


class TestAnchorLabeling:
    def test_section_anchor_attached_to_block(self):
        v1 = [_page(4, (1, "SEC. 101. body text"), (2, "old body line"))]
        v2 = [_page(4, (1, "SEC. 101. body text"), (2, "new body line"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.v1_anchor == Anchor(4, 1, "section", "SEC. 101")
        assert h.v2_anchor == Anchor(4, 1, "section", "SEC. 101")

    def test_unresolvable_anchor_returns_none_for_preamble_block(self):
        # No SEC. / TITLE / account anywhere — entire content is the
        # preamble, with anchor=None.
        v1 = [_page(47, (18, "old typographic edit"))]
        v2 = [_page(47, (18, "new typographic edit"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.v1_anchor is None
        assert h.v2_anchor is None


class TestNumericClassification:
    def test_dollar_amount_change_populates_amount_pairs(self):
        v1 = [_page(2, (14, "SEC. 101. heading"), (15, "appropriated $281,358,000 for"))]
        v2 = [_page(2, (14, "SEC. 101. heading"), (15, "appropriated $249,708,000 for"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.amount_pairs == ((281358000, 249708000),)

    def test_no_amount_change_leaves_pairs_empty(self):
        v1 = [_page(2, (14, "SEC. 101. heading"), (15, "the program shall be operated"))]
        v2 = [_page(2, (14, "SEC. 101. heading"), (15, "the program may be operated"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.amount_pairs == ()

    def test_unchanged_amount_preserved_alongside_changed_amount(self):
        # When a hunk's body changes one amount but leaves another stable,
        # both pairs survive — including the unchanged one. Renderer parity
        # with the XML callout (which shows `$X → $X (+$0)` rows for stable
        # amounts in modified sections).
        v1 = [_page(2, (14, "SEC. 101. heading"), (15, "$100,000,000 of which $5,000,000 shall remain"))]
        v2 = [_page(2, (14, "SEC. 101. heading"), (15, "$200,000,000 of which $5,000,000 shall remain"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert (100_000_000, 200_000_000) in h.amount_pairs
        assert (5_000_000, 5_000_000) in h.amount_pairs


class TestMovedClassification:
    def test_renumbered_section_at_same_position_classified_as_moved(self):
        # When a SEC. number changes but body is identical and it's at the
        # same alignment position, block keys differ → SequenceMatcher emits
        # one replace → _hunk_for_paired_blocks classifies as moved.
        v1 = [_page(63, (17, "SEC. 414. None of the funds may be used to enforce X policy"))]
        v2 = [_page(65, (4, "SEC. 413. None of the funds may be used to enforce X policy"))]
        h = diff_pdfs(v1, v2).hunks[0]
        assert h.change_type == "moved"
        assert h.v1_anchor and h.v1_anchor.text == "SEC. 414"
        assert h.v2_anchor and h.v2_anchor.text == "SEC. 413"


class TestReconcileMoves:
    def test_remove_then_add_at_distant_position_pairs_as_moved(self):
        # v1 has SEC. 414 mid-document; v2 drops it and adds SEC. 413 with the
        # same body at a later position. Block keys differ enough that
        # SequenceMatcher emits delete + insert separately; reconcile_moves
        # pairs them.
        body = "None of the funds may be used to enforce X policy"
        v1 = [
            _page(63, (1, "SEC. 100. shared header"), (17, "SEC. 414. " + body), (20, "SEC. 999. shared tail")),
        ]
        v2 = [
            _page(63, (1, "SEC. 100. shared header"), (20, "SEC. 999. shared tail")),
            _page(65, (4, "SEC. 413. " + body)),
        ]
        result = diff_pdfs(v1, v2)
        moved = [h for h in result.hunks if h.change_type == "moved"]
        assert len(moved) == 1
        assert moved[0].v1_anchor and moved[0].v1_anchor.text == "SEC. 414"
        assert moved[0].v2_anchor and moved[0].v2_anchor.text == "SEC. 413"


class TestPdfDiffSummary:
    def test_summary_counts_by_change_type(self):
        v1 = [
            _page(1, (1, "SEC. 101. heading"), (2, "old body"), (3, "SEC. 102. unchanged"), (4, "stable")),
        ]
        v2 = [
            _page(
                1,
                (1, "SEC. 101. heading"),
                (2, "new body"),
                (3, "SEC. 102. unchanged"),
                (4, "stable"),
                (5, "SEC. 103. brand new"),
                (6, "new content"),
            ),
        ]
        result = diff_pdfs(v1, v2)
        assert result.summary == {"modified": 1, "added": 1}
