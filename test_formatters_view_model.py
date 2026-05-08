"""Tests for formatters.view_model.

Step 2 of the renderer consolidation: a neutral data shape that both the
XML and PDF adapters target, and that the unified renderer consumes.
"""

import pytest
from formatters.view_model import ChangeView, DiffView


def _minimal_change(**overrides) -> ChangeView:
    base = dict(
        change_type="modified",
        heading_html="TITLE I &gt; SEC. 101",
        nav_label_html="101 - TITLE I &gt; SEC. 101",
        nav_extra_class="",
        group_key="title-i/sec-101",
        section_number="101",
        old_text="old prose",
        new_text="new prose",
        citation_html=None,
        degraded=False,
        amount_pairs=(),
        has_amendment_annotations=False,
        summary_amount_filter="amounts_changed",
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
        citation_html='<div class="citation"><span class="v1">p.1 L1</span></div>',
        degraded=True,
        nav_extra_class="unanchored",
        summary_amount_filter="real_change",
        amount_pairs=((1000, 2000), (None, 500)),
    )
    assert cv.citation_html is not None
    assert cv.degraded is True
    assert cv.nav_extra_class == "unanchored"
    assert cv.amount_pairs == ((1000, 2000), (None, 500))


def test_diff_view_holds_metadata_and_changes():
    dv = DiffView(
        bill_type="hr",
        bill_number=1234,
        congress=119,
        v1_label="Reported in House",
        v2_label="Engrossed in House",
        summary={"added": 2, "removed": 1, "modified": 5, "moved": 0},
        changes=(_minimal_change(), _minimal_change(change_type="added")),
    )
    assert dv.bill_number == 1234
    assert dv.summary["modified"] == 5
    assert len(dv.changes) == 2
    assert dv.changes[1].change_type == "added"


def test_diff_view_is_frozen():
    dv = DiffView(
        bill_type="hr",
        bill_number=1,
        congress=119,
        v1_label="v1",
        v2_label="v2",
        summary={"added": 0, "removed": 0, "modified": 0, "moved": 0},
        changes=(),
    )
    with pytest.raises(Exception):
        dv.bill_number = 2  # type: ignore[misc]
