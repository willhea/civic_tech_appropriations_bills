"""Tests for formatters.pdf_html — structural assertions on rendered HTML."""

from __future__ import annotations

from diff_pdf import PdfDiff, PdfHunk
from formatters.pdf_html import _build_card, _build_financial_summary, format_pdf_html
from parsers.pdf_anchors import Anchor


def _empty_diff() -> PdfDiff:
    return PdfDiff(hunks=())


def _diff_with(hunks, v1_anchors=(), v2_anchors=()) -> PdfDiff:
    return PdfDiff(hunks=tuple(hunks), v1_anchors=tuple(v1_anchors), v2_anchors=tuple(v2_anchors))


class TestModifiedCard:
    def test_renders_word_diff_and_citation(self):
        anchor_v1 = Anchor(2, 14, "section", "SEC. 101")
        anchor_v2 = Anchor(2, 14, "section", "SEC. 101")
        hunk = PdfHunk(
            change_type="modified",
            v1_anchor=anchor_v1,
            v2_anchor=anchor_v2,
            v1_range=(2, 14, 2, 14),
            v2_range=(2, 14, 2, 14),
            v1_text="the Secretary shall increase",
            v2_text="the Secretary may increase",
            amount_pairs=(),
        )
        html = _build_card(hunk, 0, (anchor_v1,), (anchor_v2,))
        assert "badge-modified" in html
        assert 'class="citation"' in html
        assert "p.2 L14" in html
        assert "<del>" in html and "<ins>" in html
        assert "shall" in html and "may" in html


class TestAddedCard:
    def test_added_shows_v2_text_only(self):
        anchor_v2 = Anchor(100, 23, "section", "SEC. 558")
        hunk = PdfHunk(
            change_type="added",
            v1_anchor=None,
            v2_anchor=anchor_v2,
            v1_range=None,
            v2_range=(100, 23, 100, 25),
            v1_text="",
            v2_text="SEC. 558. None of the funds may be used for the Inclusion Action Committee.",
            amount_pairs=(),
        )
        html = _build_card(hunk, 0, (), (anchor_v2,))
        assert "badge-added" in html
        assert "added-text" in html
        assert "Inclusion Action Committee" in html
        assert "(new in v2)" in html


class TestMovedCardShowsRenumber:
    def test_renumber_label_uses_anchor_text(self):
        v1_anchor = Anchor(63, 17, "section", "SEC. 414")
        v2_anchor = Anchor(65, 4, "section", "SEC. 413")
        hunk = PdfHunk(
            change_type="moved",
            v1_anchor=v1_anchor,
            v2_anchor=v2_anchor,
            v1_range=(63, 17, 63, 22),
            v2_range=(65, 4, 65, 9),
            v1_text="SEC. 414. None of the funds may be used to enforce X",
            v2_text="SEC. 413. None of the funds may be used to enforce X",
            amount_pairs=(),
        )
        html = _build_card(hunk, 0, (v1_anchor,), (v2_anchor,))
        assert "badge-moved" in html
        assert "Renumbered" in html
        assert "SEC. 414" in html and "SEC. 413" in html


class TestDegradedAnchor:
    def test_unanchored_card_styled_distinctly(self):
        hunk = PdfHunk(
            change_type="modified",
            v1_anchor=None,
            v2_anchor=None,
            v1_range=(47, 18, 47, 19),
            v2_range=(49, 4, 49, 5),
            v1_text="any facility",
            v2_text="each facility",
            amount_pairs=(),
        )
        html = _build_card(hunk, 0, (), ())
        assert "unanchored" in html
        assert "anchor unresolved" in html


class TestFinancialSummary:
    def test_empty_when_only_annotation_pairs(self):
        # Floor-amendment-only hunk — no row in financial summary table.
        hunk = PdfHunk(
            change_type="modified",
            v1_anchor=None,
            v2_anchor=None,
            v1_range=(2, 14, 2, 14),
            v2_range=(2, 14, 2, 14),
            v1_text="$281,358,000",
            v2_text="$281,358,000 (reduced by $20,000,000)",
            amount_pairs=((None, 20000000),),
        )
        diff = _diff_with([hunk])
        assert _build_financial_summary(diff) == ""

    def test_renders_row_for_real_base_change(self):
        hunk = PdfHunk(
            change_type="modified",
            v1_anchor=None,
            v2_anchor=None,
            v1_range=(2, 14, 2, 14),
            v2_range=(2, 14, 2, 14),
            v1_text="$281,358,000",
            v2_text="$249,708,000",
            amount_pairs=((281358000, 249708000),),
        )
        diff = _diff_with([hunk])
        html = _build_financial_summary(diff)
        assert "Financial Summary" in html
        assert "$281,358,000" in html
        assert "$249,708,000" in html
        assert "decrease" in html


class TestFullDocument:
    def test_format_pdf_html_assembles_full_document(self):
        html = format_pdf_html(_empty_diff(), bill_type="hr", bill_number=8752, congress=118)
        assert "<!DOCTYPE html>" in html
        assert "HR 8752" in html
        assert "PDF Comparison" in html
        assert "No changes detected" in html

    def test_summary_bar_counts_change_types(self):
        h_mod = PdfHunk("modified", None, None, (1, 1, 1, 1), (1, 1, 1, 1), "a", "b", ())
        h_add = PdfHunk("added", None, None, None, (1, 2, 1, 2), "", "c", ())
        diff = _diff_with([h_mod, h_add])
        html = format_pdf_html(diff, bill_type="hr", bill_number=1, congress=119)
        assert ">modified</span> <strong>1</strong>" in html
        assert ">added</span> <strong>1</strong>" in html
