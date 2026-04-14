"""Tests for HTML bill diff report formatter."""

from formatters.html import build_financial_table, word_diff


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


def _change(*, change_type="modified", path=None, financial=None, index=0):
    """Build a minimal change dict for testing."""
    return {
        "display_path_old": path or ["DEPT", "Section"],
        "display_path_new": path or ["DEPT", "Section"],
        "match_path": [p.lower() for p in (path or ["DEPT", "Section"])],
        "change_type": change_type,
        "old_text": "old",
        "new_text": "new",
        "text_diff": [],
        "section_number": "",
        "element_id_old": f"old-{index}",
        "element_id_new": f"new-{index}",
        **({"financial": financial} if financial else {}),
    }


class TestBuildFinancialTable:
    def test_single_amount_row(self):
        changes = [_change(financial={
            "old_amounts": [1000000],
            "new_amounts": [2000000],
            "amounts_changed": True,
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
        })]
        html = build_financial_table(changes)
        assert "$1,000,000" in html
        assert "$500,000" in html
        assert "$2,000,000" in html
        assert "$600,000" in html

    def test_mismatched_amount_counts(self):
        changes = [_change(financial={
            "old_amounts": [1000000, 500000],
            "new_amounts": [2000000, 600000, 300000],
            "amounts_changed": True,
        })]
        html = build_financial_table(changes)
        # Should render without error and include all amounts
        assert "$300,000" in html
        assert "$1,000,000" in html

    def test_added_section_no_old_amounts(self):
        changes = [_change(
            change_type="added",
            financial={
                "old_amounts": [],
                "new_amounts": [5000000],
                "amounts_changed": True,
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
        })]
        html = build_financial_table(changes)
        assert 'href="#change-0"' in html

    def test_percentage_change(self):
        changes = [_change(financial={
            "old_amounts": [1000000],
            "new_amounts": [1500000],
            "amounts_changed": True,
        })]
        html = build_financial_table(changes)
        assert "50.0%" in html
