"""Smoke tests that ChangeView/DiffView can be constructed in the shapes
adapters produce. Field semantics (PDF-only vs XML-only fields) are
covered by the adapter test suites; renderer behavior is covered by
test_formatters_diff_html_*."""

from formatters.view_model import ChangeView, DiffView


def test_change_view_constructs_with_pdf_only_fields():
    cv = ChangeView(
        change_type="modified",
        heading_html="TITLE I &gt; SEC. 101",
        nav_label_html="TITLE I &gt; SEC. 101",
        section_number="",
        citation_html='<div class="citation"><span class="v1">p.1 L1</span></div>',
        degraded=True,
        move_info_html="",
        old_text="old",
        new_text="new",
        amount_pairs=((1000, 2000),),
    )
    assert cv.degraded is True
    assert cv.amount_pairs == ((1000, 2000),)


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
