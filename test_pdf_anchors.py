"""Unit tests for PDF anchor extraction.

Anchors are landmark labels (`TITLE`, `SEC.`, account headings) that the PDF
reliably carries and the diff layer attaches to hunks as a "where am I" label.
"""

from __future__ import annotations

from parsers.pdf_anchors import Anchor, _scan_anchors_in_page


class TestTitleAnchor:
    def test_simple_title(self):
        text = "1 some preamble\n7 TITLE I\n8 DEPARTMENTAL MANAGEMENT"
        anchors = _scan_anchors_in_page(2, text)
        assert Anchor(2, 7, "title", "TITLE I") in anchors

    def test_title_with_higher_numerals(self):
        text = "3 TITLE IV\n4 RESEARCH AND DEVELOPMENT"
        anchors = _scan_anchors_in_page(40, text)
        titles = [a for a in anchors if a.kind == "title"]
        assert titles == [Anchor(40, 3, "title", "TITLE IV")]

    def test_title_must_be_at_line_start(self):
        text = "1 within the TITLE I provisions, certain things apply"
        anchors = _scan_anchors_in_page(5, text)
        assert not any(a.kind == "title" for a in anchors)


class TestSectionAnchor:
    def test_three_digit_section(self):
        text = "5 SEC. 406. Notwithstanding the numerical limitation"
        anchors = _scan_anchors_in_page(61, text)
        sections = [a for a in anchors if a.kind == "section"]
        assert sections == [Anchor(61, 5, "section", "SEC. 406")]

    def test_section_word_form(self):
        text = "1 SECTION 1. Short title"
        anchors = _scan_anchors_in_page(1, text)
        sections = [a for a in anchors if a.kind == "section"]
        assert sections == [Anchor(1, 1, "section", "SECTION 1")]

    def test_section_must_be_at_line_start(self):
        # `section 287(g)` mid-paragraph is a citation, not a heading.
        text = "12 the delegation of law enforcement authority provided by section 287(g)"
        anchors = _scan_anchors_in_page(15, text)
        assert not any(a.kind == "section" for a in anchors)


class TestAccountAnchor:
    def test_uppercase_heading_before_for_necessary_expenses(self):
        # A common GPO pattern: an all-caps account heading followed within
        # a few lines by `For necessary expenses of …`.
        text = (
            "11 OFFICE OF THE SECRETARY AND EXECUTIVE\n"
            "12 MANAGEMENT\n"
            "13 OPERATIONS AND SUPPORT\n"
            "14 For necessary expenses of the Office of the Secretary"
        )
        anchors = _scan_anchors_in_page(2, text)
        accounts = [a for a in anchors if a.kind == "account"]
        # The heading immediately preceding `For necessary expenses of` is the
        # closest account label. The plan accepts misses; require at least one
        # uppercase heading line is found and stored as an account.
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in accounts)

    def test_no_account_when_no_for_necessary_expenses(self):
        # Without the trigger phrase, uppercase lines may be titles or other
        # display headings; the heuristic should not produce account anchors.
        text = "7 TITLE I\n8 DEPARTMENTAL MANAGEMENT, INTEL-\n9 LIGENCE"
        anchors = _scan_anchors_in_page(2, text)
        assert not any(a.kind == "account" for a in anchors)

    def test_account_heading_below_section_break(self):
        text = (
            "5 SEC. 101. Short title.\n"
            "6 U.S. CUSTOMS AND BORDER PROTECTION\n"
            "7 OPERATIONS AND SUPPORT\n"
            "8 For necessary expenses of U.S. Customs and Border Protection"
        )
        anchors = _scan_anchors_in_page(11, text)
        accounts = [a for a in anchors if a.kind == "account"]
        assert any(a.text == "OPERATIONS AND SUPPORT" for a in accounts)


class TestPageChromeIgnored:
    def test_top_of_page_number_does_not_become_anchor(self):
        # Standalone page number at top
        text = "63\n1 SEC. 414. None of the funds"
        anchors = _scan_anchors_in_page(63, text)
        # Only the SEC. anchor; no spurious title/account from the bare "63"
        assert anchors == [Anchor(63, 1, "section", "SEC. 414")]

    def test_footer_chrome_does_not_become_anchor(self):
        text = "5 SEC. 200. text\n•HR 8752 RH\nVerDate Sep 11 2014 23:10 Jun 14, 2024 Jkt 049200"
        anchors = _scan_anchors_in_page(20, text)
        # The SEC. anchor is found; •HR/VerDate lines yield nothing.
        assert anchors == [Anchor(20, 5, "section", "SEC. 200")]


class TestAnchorOrderingWithinPage:
    def test_anchors_returned_in_line_order(self):
        text = (
            "1 TITLE II\n"
            "2 SECURITY, ENFORCEMENT, AND INVESTIGATIONS\n"
            "3 U.S. CUSTOMS AND BORDER PROTECTION\n"
            "4 OPERATIONS AND SUPPORT\n"
            "5 For necessary expenses of U.S. Customs and Border Protection\n"
            "20 SEC. 201. text"
        )
        anchors = _scan_anchors_in_page(11, text)
        line_numbers = [a.line_number for a in anchors]
        assert line_numbers == sorted(line_numbers)
