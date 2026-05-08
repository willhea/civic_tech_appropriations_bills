"""Tests for formatters._text, the shared text-rendering helpers.

Step 1 of the renderer consolidation: word_diff and fmt_dollar should live
in a neutral module that both pipelines import from, with backward-compatible
re-exports kept in formatters.html and formatters.pdf_html.
"""

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


def test_html_module_reexports_helpers():
    from formatters import _text
    from formatters import html as html_mod

    assert html_mod.word_diff is _text.word_diff
    assert html_mod.fmt_dollar is _text.fmt_dollar


def test_pdf_html_module_reexports_helpers():
    from formatters import _text
    from formatters import pdf_html as pdf_mod

    assert pdf_mod.word_diff is _text.word_diff
    assert pdf_mod.fmt_dollar is _text.fmt_dollar
