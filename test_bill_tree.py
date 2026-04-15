import xml.etree.ElementTree as ET

import pytest

from pathlib import Path

from bill_tree import (
    BillNode,
    BillTree,
    _extract_appropriations_text,
    extract_text_content,
    find_bill_body,
    get_header_text,
    normalize_bill,
    normalize_header,
    walk_body_sections,
    walk_title,
)


class TestNormalizeHeader:
    def test_lowercase(self):
        assert normalize_header("DEPARTMENT OF DEFENSE") == "department of defense"

    def test_collapse_whitespace(self):
        assert normalize_header(" Military  construction,\n army ") == "military construction, army"

    def test_empty_string(self):
        assert normalize_header("") == ""

    def test_mixed_case_and_whitespace(self):
        assert normalize_header("  Veterans Health  Administration  ") == "veterans health administration"


class TestExtractTextContent:
    def test_simple_text(self):
        el = ET.fromstring("<text>Hello world</text>")
        assert extract_text_content(el) == "Hello world"

    def test_nested_elements(self):
        el = ET.fromstring("<text>For <short-title>Department of Defense</short-title> purposes</text>")
        assert extract_text_content(el) == "For Department of Defense purposes"

    def test_tail_text(self):
        el = ET.fromstring("<text>Before <emphasis>bold</emphasis> after</text>")
        assert extract_text_content(el) == "Before bold after"

    def test_empty_element(self):
        el = ET.fromstring("<text/>")
        assert extract_text_content(el) == ""

    def test_whitespace_normalized(self):
        el = ET.fromstring("<text>Code— (1)provides  assistance</text>")
        assert extract_text_content(el) == "Code—(1)provides assistance"

    def test_newlines_collapsed(self):
        el = ET.fromstring("<text>first line\n  second line\n  third</text>")
        assert extract_text_content(el) == "first line second line third"

    def test_nested_whitespace_normalized(self):
        el = ET.fromstring(
            "<text>Suicidology.(b) <enum>(1)</enum>None  of the funds</text>"
        )
        assert extract_text_content(el) == "Suicidology.(b)(1)None of the funds"

    def test_list_marker_spacing_normalized(self):
        el = ET.fromstring("<text>and (2)adheres to all</text>")
        assert extract_text_content(el) == "and(2)adheres to all"

    def test_roman_numeral_marker_normalized(self):
        el = ET.fromstring("<text>Code— (iv)the term</text>")
        assert extract_text_content(el) == "Code—(iv)the term"

    def test_uppercase_marker_normalized(self):
        el = ET.fromstring("<text>and (B)the term</text>")
        assert extract_text_content(el) == "and(B)the term"

    def test_acronym_spacing_kept(self):
        el = ET.fromstring("<text>Rural Housing Service (RHS) provides</text>")
        assert extract_text_content(el) == "Rural Housing Service (RHS) provides"

    def test_year_spacing_kept(self):
        el = ET.fromstring("<text>Stat. 4302 (2008) and</text>")
        assert extract_text_content(el) == "Stat. 4302 (2008) and"

    def test_long_parenthetical_spacing_kept(self):
        el = ET.fromstring("<text>the (Comptroller) shall</text>")
        assert extract_text_content(el) == "the (Comptroller) shall"


class TestGetHeaderText:
    def test_with_header(self):
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Military construction, army</header>"
            "<text>Some text</text>"
            "</appropriations-intermediate>"
        )
        assert get_header_text(el) == "Military construction, army"

    def test_without_header(self):
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<text>Some text</text>"
            "</appropriations-intermediate>"
        )
        assert get_header_text(el) == ""

    def test_header_with_nested_elements(self):
        el = ET.fromstring(
            "<appropriations-major>"
            "<header>Department of <short-title>Veterans Affairs</short-title></header>"
            "</appropriations-major>"
        )
        assert get_header_text(el) == "Department of Veterans Affairs"


class TestExtractAppropriationsText:
    def test_text_with_paragraphs(self):
        """Element with <text> and <paragraph> children captures all content."""
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Office of the Attending Physician</header>"
            "<text>For medical supplies, including:</text>"
            "<paragraph><enum>(1)</enum><text>$9,120 per annum</text></paragraph>"
            "<paragraph><enum>(2)</enum><text>$2,800,000 for reimbursement</text></paragraph>"
            "</appropriations-intermediate>"
        )
        result = _extract_appropriations_text(el)
        assert "For medical supplies, including:" in result
        assert "$9,120" in result
        assert "$2,800,000" in result

    def test_text_only(self):
        """Element with only <text> child returns same as extract_text_content."""
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Medical services</header>"
            "<text>For necessary expenses, $60,000,000.</text>"
            "</appropriations-intermediate>"
        )
        result = _extract_appropriations_text(el)
        assert result == "For necessary expenses, $60,000,000."

    def test_paragraphs_only(self):
        """Element with only <paragraph> children still returns content."""
        el = ET.fromstring(
            "<appropriations-intermediate>"
            "<header>Some heading</header>"
            "<paragraph><enum>(1)</enum><text>First item $1,000</text></paragraph>"
            "<paragraph><enum>(2)</enum><text>Second item $2,000</text></paragraph>"
            "</appropriations-intermediate>"
        )
        result = _extract_appropriations_text(el)
        assert "$1,000" in result
        assert "$2,000" in result

    def test_empty_element(self):
        """Element with only a header returns empty string."""
        el = ET.fromstring(
            "<appropriations-major>"
            "<header>Department of Defense</header>"
            "</appropriations-major>"
        )
        result = _extract_appropriations_text(el)
        assert result == ""

    def test_excludes_enum_and_header(self):
        """Top-level enum and header are excluded from output."""
        el = ET.fromstring(
            "<appropriations-small>"
            "<enum>A</enum>"
            "<header>Salaries</header>"
            "<text>For expenses, $500,000.</text>"
            "</appropriations-small>"
        )
        result = _extract_appropriations_text(el)
        assert result == "For expenses, $500,000."
        assert "Salaries" not in result


class TestFindBillBody:
    def test_bill_with_legis_body(self):
        root = ET.fromstring(
            '<bill bill-stage="Enrolled-Bill">'
            "<legis-body><section><text>Content</text></section></legis-body>"
            "</bill>"
        )
        body = find_bill_body(root)
        assert body.tag == "legis-body"
        assert body.find("section") is not None

    def test_amendment_doc(self):
        root = ET.fromstring(
            '<amendment-doc amend-type="engrossed-amendment">'
            "<engrossed-amendment-body>"
            "<amendment>"
            '<amendment-block style="OLC">'
            "<section><text>Content</text></section>"
            "</amendment-block>"
            "</amendment>"
            "</engrossed-amendment-body>"
            "</amendment-doc>"
        )
        body = find_bill_body(root)
        assert body.tag == "amendment-block"
        assert body.find("section") is not None

    def test_amendment_block_with_nested_legis_body(self):
        """Amendment-block containing legis-body should return the legis-body."""
        root = ET.fromstring(
            '<amendment-doc amend-type="engrossed-amendment">'
            "<engrossed-amendment-body>"
            "<amendment>"
            '<amendment-block style="OLC">'
            "<legis-body><section><text>Content</text></section></legis-body>"
            "</amendment-block>"
            "</amendment>"
            "</engrossed-amendment-body>"
            "</amendment-doc>"
        )
        body = find_bill_body(root)
        assert body.find("section") is not None

    def test_amendment_doc_115_hr_244_v5_produces_nodes(self):
        """Real bill 115-hr-244 v5 should produce nodes (was 0 before fix)."""
        xml_path = Path("bills/115-hr-244/5_engrossed-amendment-house.xml")
        if not xml_path.exists():
            pytest.skip("Bill XML not available locally")
        tree = normalize_bill(xml_path)
        assert len(tree.nodes) >= 5

    def test_missing_body_raises(self):
        root = ET.fromstring("<bill><metadata/></bill>")
        with pytest.raises(ValueError, match="Could not find bill body"):
            find_bill_body(root)


class TestWalkTitle:
    """Test walk_title with inline XML mimicking real bill structure."""

    def test_basic_intermediate_with_text(self):
        """An intermediate with header and text produces one BillNode."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            '<text display-inline="no-display-inline">'
            "For acquisition, construction, $1,876,875,000, to remain available."
            "</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPARTMENT OF DEFENSE", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert node.match_path == ("department of defense", "military construction, army")
        assert node.display_path == ("DEPARTMENT OF DEFENSE", "Military construction, army")
        assert node.tag == "appropriations-intermediate"
        assert node.element_id == "AI1"
        assert node.header_text == "Military construction, army"
        assert "$1,876,875,000" in node.body_text
        assert node.section_number == ""

    def test_major_sets_context_for_intermediate(self):
        """Major without text sets context; intermediate inherits it in match_path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>II</enum>"
            "<header>VETERANS AFFAIRS</header>"
            '<appropriations-major id="AM1">'
            "<header>Veterans Health Administration</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Medical services</header>"
            '<text>For necessary expenses, $60,000,000.</text>'
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "VETERANS AFFAIRS", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert node.match_path == (
            "veterans affairs",
            "veterans health administration",
            "medical services",
        )
        assert node.display_path == (
            "VETERANS AFFAIRS",
            "Veterans Health Administration",
            "Medical services",
        )

    def test_major_with_text_produces_node(self):
        """A major with a text child produces its own node."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Big Agency</header>"
            "<text>For expenses, $500,000.</text>"
            "</appropriations-major>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert nodes[0].match_path == ("dept", "big agency")
        assert nodes[0].header_text == "Big Agency"

    def test_context_only_element_no_node(self):
        """A major with no text child sets context but produces no node."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Context Only</header>"
            "</appropriations-major>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 0

    def test_parenthetical_header_inherits_previous(self):
        """Parenthetical header like (INCLUDING TRANSFER) uses previous sibling name."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Regular Account</header>"
            "<text>For expenses, $100,000.</text>"
            "</appropriations-intermediate>"
            '<appropriations-intermediate id="AI2">'
            "<header>(INCLUDING TRANSFER OF FUNDS)</header>"
            "<text>Of the funds, not more than $50,000 may transfer.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 2
        # Second node inherits previous sibling's header for matching
        assert nodes[1].match_path == ("dept", "regular account")
        assert nodes[1].header_text == "(INCLUDING TRANSFER OF FUNDS)"

    def test_section_with_enum(self):
        """A section produces a node with section_number in the path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Admin Provisions</header>"
            "</appropriations-intermediate>"
            '<section id="S1">'
            "<enum>124.</enum>"
            "<header>Limitation on funds</header>"
            "<text>None of the funds may be used for bonuses.</text>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert node.section_number == "Sec. 124"
        assert node.match_path == ("dept", "admin provisions", "sec. 124")
        assert "bonuses" in node.body_text

    def test_division_label_in_display_path(self):
        """When division_label is provided, it prefixes the display_path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Account</header>"
            "<text>For expenses, $1,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "Division A: MilCon-VA")
        assert len(nodes) == 1
        assert nodes[0].display_path == ("Division A: MilCon-VA", "DEPT", "Account")
        # match_path never includes division
        assert nodes[0].match_path == ("dept", "account")

    def test_small_under_intermediate_context(self):
        """A small element uses the current intermediate context in its path."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub-Agency</header>"
            "</appropriations-intermediate>"
            '<appropriations-small id="AS1">'
            "<header>Tiny Program</header>"
            "<text>For grants, $10,000.</text>"
            "</appropriations-small>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert nodes[0].match_path == ("dept", "sub-agency", "tiny program")

    def test_section_with_subsections_no_direct_text(self):
        """Sections with subsections but no direct <text> should still produce a node."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<section id="S1">'
            "<enum>2.</enum>"
            "<header>Sanctions</header>"
            "<subsection>"
            "<text>The President shall impose sanctions.</text>"
            "</subsection>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert "President shall impose sanctions" in nodes[0].body_text

    def test_major_resets_intermediate(self):
        """A new major clears intermediate context."""
        title = ET.fromstring(
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPT</header>"
            '<appropriations-major id="AM1">'
            "<header>Agency A</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub A</header>"
            "<text>Text A $100.</text>"
            "</appropriations-intermediate>"
            '<appropriations-major id="AM2">'
            "<header>Agency B</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI2">'
            "<header>Sub B</header>"
            "<text>Text B $200.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 2
        assert nodes[0].match_path == ("dept", "agency a", "sub a")
        assert nodes[1].match_path == ("dept", "agency b", "sub b")

    def test_intermediate_with_paragraph_children(self):
        """An intermediate with <text> + <paragraph> children captures all content."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>JOINT ITEMS</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Office of the Attending Physician</header>"
            "<text>For medical supplies, including:</text>"
            "<paragraph><enum>(1)</enum>"
            "<text>$9,120 per annum for the Attending Physician</text>"
            "</paragraph>"
            "<paragraph><enum>(2)</enum>"
            "<text>$2,800,000 for reimbursement, $3,868,000 total</text>"
            "</paragraph>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "JOINT ITEMS", "")
        assert len(nodes) == 1
        node = nodes[0]
        assert "For medical supplies, including:" in node.body_text
        assert "$9,120" in node.body_text
        assert "$3,868,000" in node.body_text

    def test_section_wrapping_appropriations(self):
        """Section containing appropriations-* children produces individual nodes."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>LEGISLATIVE BRANCH</header>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<text>The following sums are appropriated.</text>"
            '<appropriations-major id="AM1">'
            "<header>House of Representatives</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>Salaries and Expenses</header>"
            "<text>For expenses, $1,200,000,000.</text>"
            "</appropriations-intermediate>"
            '<appropriations-intermediate id="AI2">'
            "<header>House Leadership Offices</header>"
            "<text>For offices, $22,000,000.</text>"
            "</appropriations-intermediate>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "LEGISLATIVE BRANCH", "")
        # Should produce: 1 section node + 2 intermediate nodes (major has no text)
        assert len(nodes) == 3
        assert nodes[0].tag == "section"
        assert nodes[0].body_text == "The following sums are appropriated."
        assert nodes[1].tag == "appropriations-intermediate"
        assert nodes[1].match_path == (
            "legislative branch", "house of representatives", "salaries and expenses",
        )
        assert "$1,200,000,000" in nodes[1].body_text
        assert nodes[2].match_path == (
            "legislative branch", "house of representatives", "house leadership offices",
        )

    def test_section_with_text_and_appropriations(self):
        """Section with own text AND appropriations produces both types of nodes."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>DEPT</header>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<text>General provision text.</text>"
            '<appropriations-intermediate id="AI1">'
            "<header>Sub Agency</header>"
            "<text>For expenses, $500,000.</text>"
            "</appropriations-intermediate>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 2
        assert nodes[0].tag == "section"
        assert nodes[0].body_text == "General provision text."
        assert nodes[1].tag == "appropriations-intermediate"
        assert "$500,000" in nodes[1].body_text

    def test_section_without_appropriations_unchanged(self):
        """Regular sections without appropriations children behave as before."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>DEPT</header>"
            '<section id="S1">'
            "<enum>101.</enum>"
            "<text>No funds may be used for X.</text>"
            "</section>"
            "</title>"
        )
        nodes = walk_title(title, "DEPT", "")
        assert len(nodes) == 1
        assert nodes[0].tag == "section"
        assert nodes[0].body_text == "No funds may be used for X."

    def test_section_wrapping_scopes_context(self):
        """Context from section-wrapped appropriations does not leak to siblings."""
        title = ET.fromstring(
            '<title id="T1">'
            "<header>LEG BRANCH</header>"
            '<appropriations-major id="AM0">'
            "<header>Senate</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI0">'
            "<header>Senate salaries</header>"
            "<text>For salaries, $100,000.</text>"
            "</appropriations-intermediate>"
            '<section id="S101">'
            "<enum>101.</enum>"
            "<text>Sums appropriated.</text>"
            '<appropriations-major id="AM1">'
            "<header>House of Representatives</header>"
            "</appropriations-major>"
            '<appropriations-intermediate id="AI1">'
            "<header>House salaries</header>"
            "<text>For salaries, $200,000.</text>"
            "</appropriations-intermediate>"
            "</section>"
            '<appropriations-intermediate id="AI2">'
            "<header>Senate office</header>"
            "<text>For offices, $300,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
        )
        nodes = walk_title(title, "LEG BRANCH", "")
        # Pre-section: intermediate under Senate context
        assert nodes[0].match_path == ("leg branch", "senate", "senate salaries")
        # Section node
        assert nodes[1].tag == "section"
        # Inside section: intermediate under House context
        assert nodes[2].match_path == (
            "leg branch", "house of representatives", "house salaries",
        )
        # After section: context reverts to Senate (not House)
        assert nodes[3].match_path == ("leg branch", "senate", "senate office")


class TestWalkBodySections:
    """Test walk_body_sections for bills with no titles (e.g., HR 2882 v1-3)."""

    def test_sections_from_body(self):
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "<text>This Act may be cited as the Udall Foundation Act.</text>"
            "</section>"
            '<section id="S2">'
            "<enum>2.</enum>"
            "<header>Reauthorization</header>"
            "<text>Section 12 is amended to read as follows.</text>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 2
        assert nodes[0].match_path == ("sec. 1",)
        assert nodes[0].section_number == "Sec. 1"
        assert nodes[0].header_text == "Short title"
        assert "Udall Foundation" in nodes[0].body_text
        assert nodes[1].match_path == ("sec. 2",)

    def test_empty_body(self):
        body = ET.fromstring("<legis-body/>")
        nodes = walk_body_sections(body)
        assert len(nodes) == 0

    def test_non_section_children_skipped(self):
        body = ET.fromstring(
            "<legis-body>"
            "<pagebreak/>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Title</header>"
            "<text>Content here.</text>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 1

    def test_section_with_subsections(self):
        """Sections with subsections but no direct <text> should still be captured."""
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S2">'
            "<enum>2.</enum>"
            "<header>Sanctions</header>"
            "<subsection>"
            "<header>In general</header>"
            "<text>The President shall impose sanctions.</text>"
            "</subsection>"
            "<subsection>"
            "<header>Penalties</header>"
            "<text>A person that violates shall be fined.</text>"
            "</subsection>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 1
        node = nodes[0]
        assert node.match_path == ("sec. 2",)
        assert node.header_text == "Sanctions"
        assert "President shall impose sanctions" in node.body_text
        assert "person that violates" in node.body_text

    def test_section_with_text_and_subsections(self):
        """Sections with both <text> and <subsection> should capture all content."""
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Reporting</header>"
            "<text>The agency shall submit a report that includes:</text>"
            "<subsection>"
            "<enum>(a)</enum>"
            "<text>a description of total expenditures of $5,000,000</text>"
            "</subsection>"
            "<subsection>"
            "<enum>(b)</enum>"
            "<text>an assessment of program effectiveness</text>"
            "</subsection>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 1
        node = nodes[0]
        assert "shall submit a report" in node.body_text
        assert "$5,000,000" in node.body_text
        assert "program effectiveness" in node.body_text

    def test_section_without_text_or_subsections(self):
        """Sections with nothing extractable are skipped."""
        body = ET.fromstring(
            "<legis-body>"
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "</section>"
            "</legis-body>"
        )
        nodes = walk_body_sections(body)
        assert len(nodes) == 0


class TestNormalizeBill:
    """Test normalize_bill with inline XML written to temp files."""

    def test_with_divisions(self, tmp_path):
        """Bill with divisions: walks titles within each division."""
        xml = (
            '<bill bill-stage="Enrolled-Bill">'
            "<form>"
            "<congress>One Hundred Eighteenth Congress</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<division id="D1">'
            "<enum>A</enum>"
            "<header>Military Construction</header>"
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            "<text>For acquisition, $1,000,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</division>"
            '<division id="D2">'
            "<enum>B</enum>"
            "<header>Agriculture</header>"
            '<title id="T2">'
            "<enum>I</enum>"
            "<header>AGRICULTURE PROGRAMS</header>"
            '<appropriations-intermediate id="AI2">'
            "<header>Farm loans</header>"
            "<text>For loans, $500,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</division>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_enrolled-bill.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.congress == 118
        assert tree.bill_type == "hr"
        assert tree.bill_number == 4366
        assert tree.version == "enrolled-bill"
        assert len(tree.nodes) == 2
        assert tree.nodes[0].match_path == ("department of defense", "military construction, army")
        assert tree.nodes[0].display_path[0] == "Division A: Military Construction"
        assert tree.nodes[1].match_path == ("agriculture programs", "farm loans")
        assert tree.nodes[1].display_path[0] == "Division B: Agriculture"

    def test_no_divisions_with_titles(self, tmp_path):
        """Bill without divisions: walks titles directly from body."""
        xml = (
            '<bill bill-stage="Reported-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 4366</legis-num>"
            "</form>"
            '<legis-body style="appropriations">'
            '<title id="T1">'
            "<enum>I</enum>"
            "<header>DEPARTMENT OF DEFENSE</header>"
            '<appropriations-intermediate id="AI1">'
            "<header>Military construction, army</header>"
            "<text>For acquisition, $1,876,875,000.</text>"
            "</appropriations-intermediate>"
            "</title>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_reported-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.congress == 118
        assert tree.version == "reported-in-house"
        assert len(tree.nodes) == 1
        assert tree.nodes[0].match_path == ("department of defense", "military construction, army")
        assert tree.nodes[0].display_path == ("DEPARTMENT OF DEFENSE", "Military construction, army")

    def test_no_titles_sections_only(self, tmp_path):
        """Bill with just sections under body (e.g., HR 2882 v1)."""
        xml = (
            '<bill bill-stage="Introduced-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 2882</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<section id="S1">'
            "<enum>1.</enum>"
            "<header>Short title</header>"
            "<text>This Act may be cited as the Udall Foundation Act.</text>"
            "</section>"
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "1_introduced-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.bill_type == "hr"
        assert tree.bill_number == 2882
        assert len(tree.nodes) == 1
        assert tree.nodes[0].match_path == ("sec. 1",)

    def test_version_from_filename(self, tmp_path):
        xml = (
            '<bill bill-stage="Engrossed-in-House">'
            "<form>"
            "<congress>118th CONGRESS</congress>"
            "<legis-num>H. R. 100</legis-num>"
            "</form>"
            '<legis-body style="OLC">'
            '<section id="S1"><enum>1.</enum><text>Text.</text></section>'
            "</legis-body>"
            "</bill>"
        )
        xml_path = tmp_path / "2_engrossed-in-house.xml"
        xml_path.write_text(xml)

        tree = normalize_bill(xml_path)
        assert tree.version == "engrossed-in-house"


REPORTED_BILL_PATH = Path("bills/118-hr-4366/1_reported-in-house.xml")
ENROLLED_BILL_PATH = Path("bills/118-hr-4366/6_enrolled-bill.xml")


@pytest.mark.skipif(not REPORTED_BILL_PATH.exists(), reason="Real XML not present")
class TestNormalizeBillIntegration:
    """Integration tests against real bill XML files."""

    def test_reported_in_house_produces_nodes(self):
        tree = normalize_bill(REPORTED_BILL_PATH)
        assert tree.congress == 118
        assert tree.bill_type == "hr"
        assert tree.bill_number == 4366
        assert tree.version == "reported-in-house"
        assert len(tree.nodes) == 164

    def test_reported_in_house_has_expected_paths(self):
        tree = normalize_bill(REPORTED_BILL_PATH)
        match_paths = [n.match_path for n in tree.nodes]
        assert ("department of defense", "military construction, army") in match_paths
        assert ("department of defense", "military construction, navy and marine corps") in match_paths
        assert ("department of veterans affairs", "veterans health administration", "medical services") in match_paths

    @pytest.mark.skipif(not ENROLLED_BILL_PATH.exists(), reason="Real XML not present")
    def test_enrolled_bill_node_count(self):
        tree = normalize_bill(ENROLLED_BILL_PATH)
        assert tree.congress == 118
        assert len(tree.nodes) == 1060

    @pytest.mark.skipif(not ENROLLED_BILL_PATH.exists(), reason="Real XML not present")
    def test_enrolled_no_empty_body_text(self):
        tree = normalize_bill(ENROLLED_BILL_PATH)
        empty = [n for n in tree.nodes if not n.body_text]
        assert empty == [], f"Nodes with empty body_text: {[n.display_path for n in empty[:5]]}"

    @pytest.mark.skipif(not ENROLLED_BILL_PATH.exists(), reason="Real XML not present")
    def test_enrolled_has_all_seven_divisions(self):
        tree = normalize_bill(ENROLLED_BILL_PATH)
        div_labels = sorted(set(
            n.display_path[0] for n in tree.nodes
            if n.display_path and n.display_path[0].startswith("Division")
        ))
        assert len(div_labels) == 7
        expected_prefixes = [
            "Division A:", "Division B:", "Division C:", "Division D:",
            "Division E:", "Division F:", "Division G:",
        ]
        for prefix in expected_prefixes:
            assert any(d.startswith(prefix) for d in div_labels), f"Missing {prefix}"

    @pytest.mark.skipif(not ENROLLED_BILL_PATH.exists(), reason="Real XML not present")
    def test_enrolled_division_node_counts(self):
        """Each division has an expected number of nodes."""
        tree = normalize_bill(ENROLLED_BILL_PATH)
        counts = {}
        for n in tree.nodes:
            div = n.display_path[0] if n.display_path else "unknown"
            counts[div] = counts.get(div, 0) + 1
        # Verify by division letter prefix
        by_letter = {}
        for div, count in counts.items():
            letter = div.split(":")[0].replace("Division ", "") if "Division" in div else div
            by_letter[letter] = count
        assert by_letter["A"] == 162
        assert by_letter["B"] == 178
        assert by_letter["C"] == 173
        assert by_letter["D"] == 107
        assert by_letter["E"] == 186
        assert by_letter["F"] == 239
        assert by_letter["G"] == 15

    @pytest.mark.skipif(not ENROLLED_BILL_PATH.exists(), reason="Real XML not present")
    def test_enrolled_content_matches_path(self):
        """Spot-check that node body_text contains content appropriate to its path."""
        tree = normalize_bill(ENROLLED_BILL_PATH)
        nodes_by_path = {n.match_path: n for n in tree.nodes}

        # MilCon Army should mention construction/public works
        army = nodes_by_path[("department of defense", "military construction, army")]
        assert "public works" in army.body_text.lower() or "construction" in army.body_text.lower()

        # VA Medical Services should mention inpatient/outpatient care
        med = nodes_by_path[("department of veterans affairs", "veterans health administration", "medical services")]
        assert "inpatient" in med.body_text.lower() or "outpatient" in med.body_text.lower()


class TestBillNodeDivisionLabel:
    def test_division_label_field_accessible(self):
        """BillNode should have a division_label field."""
        node = BillNode(
            match_path=("general provisions",),
            display_path=("Division A: Military Construction", "General Provisions"),
            tag="section",
            element_id="id1",
            header_text="General Provisions",
            body_text="Some text",
            section_number="Sec. 501",
            division_label="Division A: Military Construction, Veterans Affairs, and Related Agencies Appropriations Act, 2024",
        )
        assert node.division_label == "Division A: Military Construction, Veterans Affairs, and Related Agencies Appropriations Act, 2024"
