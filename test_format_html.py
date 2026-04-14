"""Tests for HTML bill diff report formatter."""

from formatters.html import word_diff


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
