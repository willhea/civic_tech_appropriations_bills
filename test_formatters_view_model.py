"""Tests for formatters.view_model.

A neutral data shape that both adapters target and the unified renderer
consumes. Pipeline-specific HTML fragments are pre-rendered by adapters.
"""

import pytest

from formatters.view_model import ChangeView, DiffView


def _minimal_change(**overrides) -> ChangeView:
    base = dict(
        change_type="modified",
        heading_html="TITLE I &gt; SEC. 101",
        nav_label_html="TITLE I &gt; SEC. 101",
        section_number="101",
        citation_html="",
        degraded=False,
        move_info_html="",
        old_text="old prose",
        new_text="new prose",
        amount_pairs=(),
    )
    base.update(overrides)
    return ChangeView(**base)


def test_change_view_holds_required_fields():
    cv = _minimal_change()
    assert cv.change_type == "modified"
    assert cv.heading_html == "TITLE I &gt; SEC. 101"
    assert cv.section_number == "101"
    assert cv.amount_pairs == ()
    assert cv.degraded is False


def test_change_view_is_frozen():
    cv = _minimal_change()
    with pytest.raises(Exception):
        cv.change_type = "added"  # type: ignore[misc]


def test_change_view_supports_pdf_only_fields():
    cv = _minimal_change(
        section_number="",
        citation_html='<div class="citation"><span class="v1">p.1 L1</span></div>',
        degraded=True,
        amount_pairs=((1000, 2000),),
    )
    assert cv.citation_html.startswith('<div class="citation">')
    assert cv.degraded is True
    assert cv.amount_pairs == ((1000, 2000),)


def test_diff_view_holds_metadata_and_changes():
    dv = DiffView(
        bill_type="hr",
        bill_number=1234,
        congress=119,
        v1_label="Reported in House",
        v2_label="Engrossed in House",
        v1_version_number=1,
        v2_version_number=2,
        summary={"added": 2, "removed": 1, "modified": 5, "moved": 0},
        changes=(_minimal_change(), _minimal_change(change_type="added")),
    )
    assert dv.bill_number == 1234
    assert dv.summary["modified"] == 5
    assert len(dv.changes) == 2
    assert dv.changes[1].change_type == "added"
    assert dv.v1_version_number == 1


def test_diff_view_allows_missing_version_numbers():
    """PDFs don't have version indexes; both fields should accept None."""
    dv = DiffView(
        bill_type="hr",
        bill_number=1,
        congress=119,
        v1_label="v1",
        v2_label="v2",
        v1_version_number=None,
        v2_version_number=None,
        summary={"added": 0, "removed": 0, "modified": 0, "moved": 0},
        changes=(),
    )
    assert dv.v1_version_number is None
    assert dv.v2_version_number is None


def test_diff_view_is_frozen():
    dv = DiffView(
        bill_type="hr",
        bill_number=1,
        congress=119,
        v1_label="v1",
        v2_label="v2",
        v1_version_number=None,
        v2_version_number=None,
        summary={"added": 0, "removed": 0, "modified": 0, "moved": 0},
        changes=(),
    )
    with pytest.raises(Exception):
        dv.bill_number = 2  # type: ignore[misc]
