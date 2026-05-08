"""Tests for the unified renderer's Financial Summary table.

Layout: rowspan groups multiple amount pairs from one change under a single
section cell; each row carries a data-group index for the JS column sort.
Headers are "Old Amount" / "New Amount". Only "real" amount changes (both
sides present and differing) appear — adapters pre-filter amount_pairs.
"""

from __future__ import annotations

from formatters.diff_html import _build_financial_summary
from formatters.view_model import ChangeView, DiffView


def _change(**overrides) -> ChangeView:
    base = dict(
        change_type="modified",
        heading_html="TITLE I &gt; Customs",
        nav_label_html="TITLE I &gt; Customs",
        section_number="",
        citation_html="",
        degraded=False,
        move_info_html="",
        old_text="",
        new_text="",
        amount_pairs=(),
    )
    base.update(overrides)
    return ChangeView(**base)


def _view(changes) -> DiffView:
    return DiffView(
        bill_type="hr",
        bill_number=1,
        congress=118,
        v1_label="v1",
        v2_label="v2",
        v1_version_number=None,
        v2_version_number=None,
        summary={},
        changes=tuple(changes),
    )


def test_returns_empty_when_no_changes_have_amount_pairs():
    assert _build_financial_summary(_view([])) == ""
    assert _build_financial_summary(_view([_change()])) == ""


def test_table_includes_canonical_headers():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert "<h2>Financial Summary</h2>" in html
    assert "<th>Section</th>" in html
    assert "<th>Old Amount</th>" in html
    assert "<th>New Amount</th>" in html
    assert "<th>Change ($)</th>" in html
    assert "<th>Change (%)</th>" in html


def test_single_pair_row_has_no_rowspan_attribute():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert "rowspan=" not in html
    # Section cell links to #change-0 with the heading as the visible label.
    assert '<a href="#change-0">TITLE I &gt; Customs</a>' in html


def test_amounts_and_change_columns_formatted():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500),))]))
    assert "$1,000" in html
    assert "$1,500" in html
    assert "+$500" in html
    assert "+50.0%" in html


def test_decrease_uses_negative_sign_outside_dollar():
    html = _build_financial_summary(_view([_change(amount_pairs=((2000, 1500),))]))
    assert "-$500" in html  # sign outside the dollar formatter
    assert "-25.0%" in html


def test_multi_pair_change_uses_rowspan_for_section_cell():
    html = _build_financial_summary(_view([_change(amount_pairs=((1000, 1500), (2000, 3000)))]))
    # First row carries the section cell with rowspan=2.
    assert 'rowspan="2"' in html
    # Section label appears exactly once even though there are two pairs.
    assert html.count("TITLE I &gt; Customs") == 1
    # Two data rows.
    assert html.count("<tr ") == 2


def test_data_group_attribute_set_per_change():
    """The data-group attr lets the JS sort cluster multi-pair rows together."""
    html = _build_financial_summary(
        _view(
            [
                _change(amount_pairs=((1000, 1500),)),
                _change(amount_pairs=((2000, 2500),)),
            ]
        )
    )
    assert 'data-group="0"' in html
    assert 'data-group="1"' in html


def test_changes_without_amount_pairs_are_skipped():
    html = _build_financial_summary(
        _view(
            [
                _change(),  # no amounts -> skipped
                _change(amount_pairs=((1000, 1500),)),
                _change(),  # no amounts -> skipped
            ]
        )
    )
    # Only the middle change shows up; its anchor is #change-1 (preserves index).
    assert '<a href="#change-1">' in html
    assert "<tr " in html
    assert html.count("<tr ") == 1


def test_zero_old_amount_yields_em_dash_percent():
    html = _build_financial_summary(_view([_change(amount_pairs=((0, 500),))]))
    # Avoids divide-by-zero; em-dash signals "n/a" for percent.
    assert "+$500" in html
    assert "—" in html


def test_increase_decrease_css_class_on_row():
    html = _build_financial_summary(
        _view(
            [
                _change(amount_pairs=((1000, 1500),)),
                _change(amount_pairs=((2000, 1500),)),
            ]
        )
    )
    assert '<tr class="increase"' in html
    assert '<tr class="decrease"' in html
