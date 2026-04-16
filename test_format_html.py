"""Tests for HTML bill diff report formatter."""

import pytest

from formatters.html import (
    build_change_card,
    build_financial_table,
    build_sidebar,
    format_html,
    word_diff,
)


class TestWordDiff:
    def test_identical_text_no_markup(self):
        result = word_diff("hello world", "hello world")
        assert "<ins>" not in result
        assert "<del>" not in result
        assert "hello world" == result

    def test_single_word_changed(self):
        result = word_diff("the cat sat", "the dog sat")
        assert "<del>cat</del>" in result
        assert "<ins>dog</ins>" in result
        assert "the" in result
        assert "sat" in result

    def test_dollar_amount_change(self):
        result = word_diff(
            "appropriated $1,000,000 for construction",
            "appropriated $2,500,000 for construction",
        )
        assert "<del>$1,000,000</del>" in result
        assert "<ins>$2,500,000</ins>" in result
        assert "appropriated" in result
        assert "for construction" in result

    def test_low_similarity_returns_none(self):
        result = word_diff(
            "this is completely different text about one topic",
            "nothing here matches the original at all whatsoever",
        )
        assert result is None

    def test_html_characters_escaped(self):
        result = word_diff(
            "amount < $1,000 & more",
            "amount < $2,000 & more",
        )
        assert "&lt;" in result
        assert "&amp;" in result
        # Should not contain raw < or & (outside of tags)
        # The <del> and <ins> tags are expected
        stripped = result.replace("<del>", "").replace("</del>", "")
        stripped = stripped.replace("<ins>", "").replace("</ins>", "")
        assert "<" not in stripped
        assert "&" in stripped  # escaped entities contain &

    def test_addition_at_end(self):
        result = word_diff("first second", "first second third")
        assert "<ins>third</ins>" in result

    def test_deletion_at_end(self):
        result = word_diff("first second third", "first second")
        assert "<del>third</del>" in result

    def test_empty_strings(self):
        result = word_diff("", "")
        assert result == ""

    def test_threshold_boundary(self):
        # Two texts that are somewhat similar but below default threshold
        # should return None
        result = word_diff("a b c d e", "v w x y z")
        assert result is None

    def test_custom_threshold(self):
        # With threshold=0.0, even very different texts produce a diff
        result = word_diff("a b c", "x y z", threshold=0.0)
        assert result is not None


from conftest import make_change_dict as _change


class TestBuildFinancialTable:
    def test_single_amount_row(self):
        changes = [_change(financial={
            "old_amounts": [1000000],
            "new_amounts": [2000000],
            "amounts_changed": True,
            "paired_amounts": [[1000000, 2000000]],
        })]
        html = build_financial_table(changes)
        assert "<table" in html
        assert "$1,000,000" in html
        assert "$2,000,000" in html
        assert "+$1,000,000" in html

    def test_multiple_amounts_sub_rows(self):
        changes = [_change(financial={
            "old_amounts": [1000000, 500000],
            "new_amounts": [2000000, 600000],
            "amounts_changed": True,
            "paired_amounts": [[1000000, 2000000], [500000, 600000]],
        })]
        html = build_financial_table(changes)
        assert "$1,000,000" in html
        assert "$500,000" in html
        assert "$2,000,000" in html
        assert "$600,000" in html

    def test_mismatched_amount_counts_with_paired(self):
        """Inserted amount appears as (None, new) via paired_amounts."""
        changes = [_change(financial={
            "old_amounts": [1000000, 500000],
            "new_amounts": [2000000, 600000, 300000],
            "amounts_changed": True,
            "paired_amounts": [[1000000, 2000000], [None, 600000], [500000, 300000]],
        })]
        html = build_financial_table(changes)
        assert "$300,000" in html
        assert "$1,000,000" in html
        assert "$600,000" in html
        # The inserted amount should show em-dash for old
        assert "\u2014" in html

    def test_fallback_to_positional_without_paired(self):
        """When paired_amounts is absent, fall back to positional pairing."""
        changes = [_change(financial={
            "old_amounts": [1000000],
            "new_amounts": [2000000],
            "amounts_changed": True,
        })]
        html = build_financial_table(changes)
        assert "$1,000,000" in html
        assert "$2,000,000" in html

    def test_added_section_no_old_amounts(self):
        changes = [_change(
            change_type="added",
            financial={
                "old_amounts": [],
                "new_amounts": [5000000],
                "amounts_changed": True,
                "paired_amounts": [[None, 5000000]],
            },
        )]
        html = build_financial_table(changes)
        assert "$5,000,000" in html
        assert "\u2014" in html  # em-dash for missing old amount

    def test_removed_section_no_new_amounts(self):
        changes = [_change(
            change_type="removed",
            financial={
                "old_amounts": [3000000],
                "new_amounts": [],
                "amounts_changed": True,
                "paired_amounts": [[3000000, None]],
            },
        )]
        html = build_financial_table(changes)
        assert "$3,000,000" in html
        assert "\u2014" in html  # em-dash for missing new amount

    def test_no_financial_changes_returns_empty(self):
        changes = [_change()]  # no financial key
        html = build_financial_table(changes)
        assert html == ""

    def test_row_links_to_change_anchor(self):
        changes = [_change(financial={
            "old_amounts": [100],
            "new_amounts": [200],
            "amounts_changed": True,
            "paired_amounts": [[100, 200]],
        })]
        html = build_financial_table(changes)
        assert 'href="#change-0"' in html

    def test_percentage_change(self):
        changes = [_change(financial={
            "old_amounts": [1000000],
            "new_amounts": [1500000],
            "amounts_changed": True,
            "paired_amounts": [[1000000, 1500000]],
        })]
        html = build_financial_table(changes)
        assert "50.0%" in html


    def test_path_not_double_escaped(self):
        """Path separators should not be double-escaped (issue #15)."""
        changes = [_change(
            path=["Division A", "Title I", "Army Operations"],
            financial={
                "old_amounts": [1000000],
                "new_amounts": [2000000],
                "amounts_changed": True,
                "paired_amounts": [[1000000, 2000000]],
            },
        )]
        html = build_financial_table(changes)
        assert "&amp;gt;" not in html
        assert "Division A" in html


class TestBuildChangeCard:
    def test_modified_has_inline_diff(self):
        change = _change(change_type="modified", index=3)
        change["old_text"] = "appropriated $1,000 for projects"
        change["new_text"] = "appropriated $2,000 for projects"
        html = build_change_card(change, 3)
        assert 'id="change-3"' in html
        assert "<del>" in html
        assert "<ins>" in html
        assert "modified" in html.lower()

    def test_modified_low_similarity_shows_blocks(self):
        change = _change(change_type="modified", index=0)
        change["old_text"] = "completely different original text here"
        change["new_text"] = "nothing matching whatsoever in replacement"
        html = build_change_card(change, 0)
        # Should fall back to old/new blocks, not inline diff
        assert "old-text" in html or "removed" in html.lower()
        assert "new-text" in html or "added" in html.lower()

    def test_added_card(self):
        change = _change(change_type="added", index=1)
        change["display_path_old"] = None
        change["new_text"] = "new section text here"
        html = build_change_card(change, 1)
        assert 'id="change-1"' in html
        assert "new section text here" in html
        assert "added" in html.lower()

    def test_removed_card(self):
        change = _change(change_type="removed", index=2)
        change["display_path_new"] = None
        change["old_text"] = "removed section text"
        html = build_change_card(change, 2)
        assert 'id="change-2"' in html
        assert "removed section text" in html
        assert "removed" in html.lower()

    def test_moved_card_shows_paths(self):
        change = _change(change_type="moved", index=0)
        change["display_path_old"] = ["Title I", "Old Section"]
        change["display_path_new"] = ["Title II", "New Section"]
        change["old_text"] = "same text"
        change["new_text"] = "same text"
        html = build_change_card(change, 0)
        assert "Old Section" in html
        assert "New Section" in html
        assert "moved" in html.lower()

    def test_moved_card_shows_body_when_text_identical(self):
        """Moved cards should show body text even when old and new text are identical."""
        change = _change(change_type="moved", index=0)
        change["display_path_old"] = ["Title I", "Sec. 5"]
        change["display_path_new"] = ["Title II", "Sec. 10"]
        change["old_text"] = "For acquisition and construction, $2,022,775,000, to remain available."
        change["new_text"] = "For acquisition and construction, $2,022,775,000, to remain available."
        html = build_change_card(change, 0)
        assert "$2,022,775,000" in html
        assert "change-body" in html

    def test_financial_callout(self):
        change = _change(
            change_type="modified",
            financial={
                "old_amounts": [1000000],
                "new_amounts": [2000000],
                "amounts_changed": True,
                "paired_amounts": [[1000000, 2000000]],
            },
        )
        change["old_text"] = "appropriated $1,000,000 total"
        change["new_text"] = "appropriated $2,000,000 total"
        html = build_change_card(change, 0)
        assert "$1,000,000" in html
        assert "$2,000,000" in html

    def test_amendment_annotation_badge_in_callout(self):
        """Financial callout should show a warning badge when amendment annotations present."""
        change = _change(
            change_type="modified",
            financial={
                "old_amounts": [287000000],
                "new_amounts": [289000000],
                "amounts_changed": True,
                "paired_amounts": [[287000000, 289000000]],
                "has_amendment_annotations": True,
            },
        )
        change["old_text"] = "$287,000,000"
        change["new_text"] = "$287,000,000 (increased by $2,000,000)"
        html = build_change_card(change, 0)
        assert "amendment" in html.lower()

    def test_no_amendment_badge_when_absent(self):
        """No amendment badge when has_amendment_annotations is False."""
        change = _change(
            change_type="modified",
            financial={
                "old_amounts": [1000000],
                "new_amounts": [2000000],
                "amounts_changed": True,
                "paired_amounts": [[1000000, 2000000]],
                "has_amendment_annotations": False,
            },
        )
        change["old_text"] = "$1,000,000"
        change["new_text"] = "$2,000,000"
        html = build_change_card(change, 0)
        assert "amendment" not in html.lower()

    def test_section_number_displayed(self):
        change = _change(index=0)
        change["section_number"] = "Sec. 101"
        html = build_change_card(change, 0)
        assert "Sec. 101" in html

    def test_html_escaped_in_text(self):
        change = _change(change_type="added", index=0)
        change["new_text"] = "amount < $1,000 & more"
        html = build_change_card(change, 0)
        assert "&lt;" in html
        assert "&amp;" in html


    def test_rows_have_group_attribute_for_sort(self):
        """Rows in a rowspan group should share a data-group attribute for JS sort."""
        change = _change(
            change_type="modified",
            financial={
                "old_amounts": [1000, 2000],
                "new_amounts": [1500, 2500],
                "amounts_changed": True,
                "paired_amounts": [[1000, 1500], [2000, 2500]],
            },
        )
        html = build_financial_table([change])
        trs = [line for line in html.split("\n") if line.strip().startswith("<tr")]
        assert len(trs) >= 2
        # Both rows should share the same data-group value
        assert 'data-group="0"' in trs[0]
        assert 'data-group="0"' in trs[1]

    def test_sub_row_amounts_have_css_class(self):
        """Sub-rows (no path cell due to rowspan) should still have colored amounts."""
        change = _change(
            change_type="modified",
            financial={
                "old_amounts": [1000, 2000],
                "new_amounts": [1500, 2500],
                "amounts_changed": True,
                "paired_amounts": [[1000, 1500], [2000, 2500]],
            },
        )
        html = build_financial_table([change])
        # Sub-row (second <tr>) has no path cell, only 4 <td>s.
        # nth-child(4) would hit wrong cell. CSS classes should work instead.
        trs = [line for line in html.split("\n") if line.strip().startswith("<tr")]
        assert len(trs) >= 2
        # Both rows should have the increase class on their amount cells
        for tr in trs:
            assert 'class="increase"' in tr or 'class="decrease"' in tr or 'class="unchanged"' in tr
            # Amount cells should have a class that CSS can target for coloring
            assert 'class="amount change-amount"' in tr

class TestBuildSidebar:
    def test_nav_items_present(self):
        changes = [
            _change(path=["Title I", "Army"], change_type="modified", index=0),
            _change(path=["Title I", "Navy"], change_type="added", index=1),
        ]
        html = build_sidebar(changes)
        assert "<nav" in html
        assert "Army" in html
        assert "Navy" in html

    def test_links_to_change_anchors(self):
        changes = [
            _change(path=["DEPT", "Section A"], index=0),
            _change(path=["DEPT", "Section B"], index=1),
        ]
        html = build_sidebar(changes)
        assert 'href="#change-0"' in html
        assert 'href="#change-1"' in html

    def test_change_type_badge(self):
        changes = [
            _change(change_type="modified", index=0),
            _change(change_type="added", index=1),
            _change(change_type="removed", index=2),
        ]
        html = build_sidebar(changes)
        assert "modified" in html.lower()
        assert "added" in html.lower()
        assert "removed" in html.lower()

    def test_display_path_joined(self):
        changes = [_change(path=["Division A", "Title I", "Army"], index=0)]
        html = build_sidebar(changes)
        # Path parts should appear (joined with some separator)
        assert "Division A" in html
        assert "Army" in html

    def test_empty_changes(self):
        html = build_sidebar([])
        assert "<nav" in html


def _sample_diff_dict(**overrides):
    """Build a minimal diff dict for testing format_html."""
    base = {
        "old_version": "reported-in-house",
        "new_version": "engrossed-in-house",
        "congress": 118,
        "bill_type": "hr",
        "bill_number": 4366,
        "summary": {"added": 1, "removed": 0, "modified": 1, "unchanged": 5, "moved": 0},
        "changes": [
            {
                "display_path_old": ["DEPT", "Army"],
                "display_path_new": ["DEPT", "Army"],
                "match_path": ["dept", "army"],
                "change_type": "modified",
                "old_text": "appropriated $1,000,000 for construction",
                "new_text": "appropriated $2,000,000 for construction",
                "text_diff": [],
                "section_number": "Sec. 101",
                "element_id_old": "old-1",
                "element_id_new": "new-1",
                "financial": {
                    "old_amounts": [1000000],
                    "new_amounts": [2000000],
                    "amounts_changed": True,
                    "paired_amounts": [[1000000, 2000000]],
                },
            },
            {
                "display_path_old": None,
                "display_path_new": ["DEPT", "Navy"],
                "match_path": ["dept", "navy"],
                "change_type": "added",
                "old_text": None,
                "new_text": "new navy section text",
                "text_diff": [],
                "section_number": "",
                "element_id_old": None,
                "element_id_new": "new-2",
            },
        ],
    }
    base.update(overrides)
    return base


class TestFormatHtml:
    def test_valid_html_structure(self):
        html = format_html(_sample_diff_dict())
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_header_shows_bill_info(self):
        html = format_html(_sample_diff_dict())
        assert "HR 4366" in html or "hr 4366" in html.lower()
        assert "118" in html
        assert "reported-in-house" in html
        assert "engrossed-in-house" in html

    def test_header_shows_version_numbers(self):
        diff = _sample_diff_dict()
        diff["old_version_number"] = 1
        diff["new_version_number"] = 2
        html = format_html(diff)
        # Should show version numbers alongside names
        assert "v1" in html.lower() or "version 1" in html.lower()
        assert "v2" in html.lower() or "version 2" in html.lower()

    def test_header_without_version_numbers(self):
        """Version numbers are optional, header still works without them."""
        diff = _sample_diff_dict()
        # No version_number keys
        html = format_html(diff)
        assert "reported-in-house" in html

    def test_summary_counts(self):
        html = format_html(_sample_diff_dict())
        assert "added" in html
        assert "modified" in html

    def test_contains_financial_table(self):
        html = format_html(_sample_diff_dict())
        assert "financial-table" in html
        assert "$1,000,000" in html

    def test_contains_sidebar(self):
        html = format_html(_sample_diff_dict())
        assert "sidebar" in html
        assert "sidebar-filter" in html

    def test_contains_change_cards(self):
        html = format_html(_sample_diff_dict())
        assert 'id="change-0"' in html
        assert 'id="change-1"' in html

    def test_contains_inline_css(self):
        html = format_html(_sample_diff_dict())
        assert "<style>" in html

    def test_contains_inline_js(self):
        html = format_html(_sample_diff_dict())
        assert "<script>" in html

    def test_no_financial_data_omits_table(self):
        diff = _sample_diff_dict()
        # Remove financial data from all changes
        for c in diff["changes"]:
            c.pop("financial", None)
        html = format_html(diff)
        assert "Financial Summary" not in html

    def test_empty_changes(self):
        diff = _sample_diff_dict(changes=[], summary={
            "added": 0, "removed": 0, "modified": 0, "unchanged": 0, "moved": 0,
        })
        html = format_html(diff)
        assert "<!DOCTYPE html>" in html
        assert "No changes found" in html


class TestCliIntegration:
    def test_format_flag_accepted(self):
        from diff_bill import build_parser
        parser = build_parser()
        args = parser.parse_args(["compare", "a.xml", "b.xml", "--format", "html"])
        assert args.format == "html"

    def test_format_default_is_html(self):
        from diff_bill import build_parser
        parser = build_parser()
        args = parser.parse_args(["compare", "a.xml", "b.xml"])
        assert args.format == "html"

    @pytest.mark.slow
    def test_format_html_output(self, tmp_path):
        """HTML format produces a valid HTML file via the CLI."""
        import subprocess
        old = "bills/118-hr-4366/1_reported-in-house.xml"
        new = "bills/118-hr-4366/2_engrossed-in-house.xml"
        import os
        if not os.path.exists(old) or not os.path.exists(new):
            import pytest
            pytest.skip("Real bill XMLs not available")

        out = tmp_path / "report.html"
        result = subprocess.run(
            ["uv", "run", "python", "diff_bill.py", "compare", old, new,
             "--format", "html", "-o", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = out.read_text()
        assert content.startswith("<!DOCTYPE html>")

    @pytest.mark.slow
    def test_format_html_v1_v2_no_phantom_financial(self, tmp_path):
        """v1 vs v2 has no real financial changes after amendment stripping."""
        import subprocess
        old = "bills/118-hr-4366/1_reported-in-house.xml"
        new = "bills/118-hr-4366/2_engrossed-in-house.xml"
        import os
        if not os.path.exists(old) or not os.path.exists(new):
            import pytest
            pytest.skip("Real bill XMLs not available")

        out = tmp_path / "report.html"
        result = subprocess.run(
            ["uv", "run", "python", "diff_bill.py", "compare", old, new,
             "--format", "html", "-o", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = out.read_text()
        # v1->v2 has floor amendment annotations that change effective amounts.
        # These are now correctly detected as financial changes.
        assert "Financial Summary" in content

    @pytest.mark.slow
    def test_format_html_v1_v6_has_financial_summary(self, tmp_path):
        """v1 vs v6 (enrolled) has genuine financial changes."""
        import subprocess
        old = "bills/118-hr-4366/1_reported-in-house.xml"
        new = "bills/118-hr-4366/6_enrolled-bill.xml"
        import os
        if not os.path.exists(old) or not os.path.exists(new):
            import pytest
            pytest.skip("Real bill XMLs not available")

        out = tmp_path / "report.html"
        result = subprocess.run(
            ["uv", "run", "python", "diff_bill.py", "compare", old, new,
             "--format", "html", "-o", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        content = out.read_text()
        assert "Financial Summary" in content
