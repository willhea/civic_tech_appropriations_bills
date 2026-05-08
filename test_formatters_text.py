"""Tests for formatters._text, the shared text-rendering helpers."""

from formatters._text import fmt_dollar, word_diff


def test_fmt_dollar_basic():
    assert fmt_dollar(1234567) == "$1,234,567"


def test_fmt_dollar_zero():
    assert fmt_dollar(0) == "$0"


def test_word_diff_returns_inline_html():
    out = word_diff("the quick brown fox", "the slow brown fox")
    assert out is not None
    assert "<del>quick</del>" in out
    assert "<ins>slow</ins>" in out


def test_word_diff_returns_none_when_too_dissimilar():
    assert word_diff("alpha beta gamma", "one two three") is None
