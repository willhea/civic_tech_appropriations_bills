"""Tests for the unified renderer's sidebar nav items and financial callout.

Sidebar: per-change <li> with optional unanchored class and section-number
prefix. Callout: flex-row layout, one row per real amount change.
"""

from __future__ import annotations

from formatters.diff_html import _build_callout, _build_nav_item, _build_sidebar
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


# ---------- Sidebar ---------------------------------------------------------


def test_nav_item_basic():
    item = _build_nav_item(_change(), 0)
    assert item.startswith('<li class="nav-item" data-type="modified">')
    assert 'href="#change-0"' in item
    assert '<span class="badge badge-modified">modified</span>' in item
    assert "TITLE I &gt; Customs" in item


def test_nav_item_section_number_prefix():
    item = _build_nav_item(_change(section_number="101"), 0)
    # Per the existing XML pipeline, section number is prefixed with " — "
    # before the path label.
    assert "101 — TITLE I &gt; Customs" in item


def test_nav_item_section_number_html_escaped():
    item = _build_nav_item(_change(section_number="<x>"), 0)
    assert "<x>" not in item
    assert "&lt;x&gt;" in item


def test_nav_item_degraded_adds_unanchored_class():
    item = _build_nav_item(
        _change(degraded=True, nav_label_html="(uncategorized) — p.2 L5"),
        0,
    )
    assert '<li class="nav-item unanchored" data-type="modified">' in item


def test_sidebar_emits_one_li_per_change():
    sidebar = _build_sidebar(_view([_change(), _change(change_type="added")]))
    assert sidebar.count("<li ") == 2
    # Ordering preserved: data-target indices line up with positions.
    assert sidebar.index('href="#change-0"') < sidebar.index('href="#change-1"')


def test_sidebar_filter_input_present():
    sidebar = _build_sidebar(_view([]))
    assert 'id="sidebar-filter"' in sidebar
    assert "<ul></ul>" in sidebar  # empty when no changes


# ---------- Callout ---------------------------------------------------------


def test_callout_empty_when_no_amount_pairs():
    assert _build_callout(_change()) == ""


def test_callout_real_change_uses_flex_row_with_delta_class():
    """Callout uses flex rows with semantic delta classes for color."""
    callout = _build_callout(_change(amount_pairs=((1000, 1500),)))
    assert callout.startswith('<div class="financial-callout">')
    assert callout.rstrip().endswith("</div>")
    assert '<div class="row">' in callout
    assert '<span class="label">Amount:</span>' in callout
    assert "$1,000 &rarr; $1,500" in callout
    # Delta has a semantic class for color.
    assert '<span class="delta increase">' in callout
    assert "(+$500)" in callout


def test_callout_decrease_uses_decrease_class_and_negative_sign():
    callout = _build_callout(_change(amount_pairs=((2000, 1500),)))
    assert '<span class="delta decrease">' in callout
    assert "(-$500)" in callout


def test_callout_multiple_pairs_emit_multiple_rows():
    callout = _build_callout(_change(amount_pairs=((1000, 1500), (2000, 3000))))
    assert callout.count('<div class="row">') == 2
    assert "$1,000 &rarr; $1,500" in callout
    assert "$2,000 &rarr; $3,000" in callout


def test_card_includes_callout_when_amounts_present():
    """The card builder integrates the callout below the body."""
    from formatters.diff_html import _build_card

    html = _build_card(
        _change(old_text="x", new_text="y", amount_pairs=((1000, 1500),)),
        0,
    )
    assert '<div class="financial-callout">' in html
    body_pos = html.index("change-body")
    callout_pos = html.index('class="financial-callout"')
    assert body_pos < callout_pos


def test_card_omits_callout_when_no_amount_pairs():
    from formatters.diff_html import _build_card

    html = _build_card(_change(old_text="x", new_text="y"), 0)
    assert "financial-callout" not in html
