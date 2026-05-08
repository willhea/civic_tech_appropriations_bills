"""Unit tests for pdf_text primitives. One test per primitive that earned its keep."""

from __future__ import annotations

from parsers.pdf_text import (
    Line,
    Page,
    normalize_glyphs,
    page_range_text,
    rejoin_soft_hyphens,
    strip_page_chrome,
)


def _page(page_number: int, text: str) -> Page:
    """Test helper: build a Page whose text round-trips through the property.

    Each newline in `text` becomes its own Line with no source line number.
    """
    return Page(page_number, tuple(Line(None, line) for line in text.split("\n")))


class TestRejoinSoftHyphens:
    def test_joins_lowercase_continuation(self):
        raw = "Representa-\ntives of the United"
        assert rejoin_soft_hyphens(raw) == "Representatives of the United"

    def test_joins_multiple_hyphens(self):
        raw = "avail-\nable until Sep-\ntember 30, 2026"
        assert rejoin_soft_hyphens(raw) == "available until September 30, 2026"

    def test_preserves_compound_with_uppercase_continuation(self):
        # GPO soft breaks always continue on a lowercase letter; uppercase
        # signals a real compound like Child-Rescue and must be preserved.
        raw = "Operative Child-\nRescue Corps"
        assert rejoin_soft_hyphens(raw) == "Operative Child-\nRescue Corps"

    def test_preserves_inline_hyphens(self):
        raw = "police-type vehicles"
        assert rejoin_soft_hyphens(raw) == "police-type vehicles"

    def test_preserves_dollar_for_dollar_inline(self):
        raw = "reduced on a dollar-for-dollar basis"
        assert rejoin_soft_hyphens(raw) == "reduced on a dollar-for-dollar basis"


class TestStripPageChrome:
    def test_strips_top_of_page_number(self):
        raw = "63\nSEC. 414. None of the funds"
        assert strip_page_chrome(raw) == "SEC. 414. None of the funds"

    def test_strips_bullet_hr_footer_and_everything_after(self):
        raw = "expenses.\n•HR 8752 RH\nVerDate Sep 11 2014 23:10 Jun 14, 2024"
        assert strip_page_chrome(raw) == "expenses."

    def test_strips_watermark_below_footer(self):
        raw = "expenses.\n•HR 8752 EH\nVerDate Sep 11 2014\nBOJ_$$\nhtiw\nDORP3WBZCZ7KSD\nno\nnosnhojk"
        assert strip_page_chrome(raw) == "expenses."

    def test_keeps_body_content_unchanged(self):
        raw = "SEC. 101. For necessary expenses of the Office."
        assert strip_page_chrome(raw) == "SEC. 101. For necessary expenses of the Office."

    def test_does_not_strip_multi_digit_inline_numbers(self):
        raw = "SEC. 101.\n2026\ncontinues"
        assert strip_page_chrome(raw) == "SEC. 101.\n2026\ncontinues"


class TestPageRangeText:
    def test_concatenates_pages_in_range(self):
        pages = [_page(1, "first"), _page(2, "second"), _page(3, "third")]
        assert page_range_text(pages, 1, 2) == "first\nsecond"

    def test_inclusive_end(self):
        pages = [_page(1, "a"), _page(2, "b"), _page(3, "c")]
        assert page_range_text(pages, 1, 3) == "a\nb\nc"

    def test_rejoins_cross_page_soft_hyphen(self):
        # Per-page cleanup leaves a trailing `-` on the prior page when the
        # break crosses a page boundary; concatenation re-creates `-\n` and
        # the helper must rejoin it.
        pages = [_page(15, "not to ex-"), _page(16, "ceed $7,650")]
        assert page_range_text(pages, 15, 16) == "not to exceed $7,650"

    def test_skips_pages_outside_range(self):
        pages = [_page(1, "a"), _page(2, "b"), _page(3, "c")]
        assert page_range_text(pages, 2, 2) == "b"


class TestNormalizeGlyphs:
    def test_em_dash_to_padded_hyphen(self):
        # GPO uses em-dash to introduce enumerated subparagraphs; readers see it
        # as " - ". Pad with spaces so whitespace-normalization handles either form.
        assert normalize_glyphs("used—(1)") == "used - (1)"

    def test_en_dash_to_padded_hyphen(self):
        # Same treatment for en-dash (U+2013), used in `H–2B`.
        assert normalize_glyphs("H–2B") == "H - 2B"

    def test_smart_singles_to_ascii_apostrophe(self):
        assert normalize_glyphs("‘foo’") == "'foo'"

    def test_smart_doubles_to_ascii_double_quote(self):
        assert normalize_glyphs("“foo”") == '"foo"'

    def test_paired_smart_singles_collapse_to_double_quote(self):
        # GPO encodes double quotes as two adjacent single-glyph smart quotes:
        # ``Asylum Program Fee'' → "Asylum Program Fee"
        assert normalize_glyphs("‘‘Asylum’’") == '"Asylum"'

    def test_preserves_ascii_hyphen(self):
        assert normalize_glyphs("police-type") == "police-type"

    def test_preserves_apostrophe_in_possessive(self):
        assert normalize_glyphs("Will's") == "Will's"
