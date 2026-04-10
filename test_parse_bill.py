import xml.etree.ElementTree as ET

from pathlib import Path

import pytest

import csv
import io

from parse_bill import (
    BillLineItems,
    CSV_COLUMNS,
    LineItem,
    build_category,
    classify_amount,
    extract_line_items_from_element,
    extract_primary_amounts,
    find_amounts,
    line_item_to_row,
    parse_bill,
    parse_dollar_amount,
    write_csv,
    parse_title,
)


class TestParseDollarAmount:
    def test_simple_amount(self):
        assert parse_dollar_amount("$1,234,567") == 1234567

    def test_large_amount(self):
        assert parse_dollar_amount("$2,022,775,000") == 2022775000

    def test_small_amount(self):
        assert parse_dollar_amount("$496,000") == 496000

    def test_no_commas(self):
        assert parse_dollar_amount("$78337") == 78337

    def test_cents_ignored(self):
        """Appropriations are whole dollars but some amounts have sub-dollar values."""
        assert parse_dollar_amount("$316,742,419") == 316742419


class TestClassifyAmount:
    def test_appropriation_default(self):
        """First amount with no qualifying keywords is an appropriation."""
        text = "$2,022,775,000, to remain available until September 30, 2028"
        assert classify_amount(text, 0, 15) == "appropriation"

    def test_rescission(self):
        text = "of the $74,004,000,000 that became available on October 1, 2023, previously appropriated under this heading, $3,034,205,000 is hereby rescinded"
        # The rescission amount starts at the second dollar sign
        start = text.index("$3,034,205,000")
        end = start + len("$3,034,205,000")
        assert classify_amount(text, start, end) == "rescission"

    def test_proviso_limit(self):
        text = "not to exceed $398,145,000 shall be available for study, planning, design"
        start = text.index("$398,145,000")
        end = start + len("$398,145,000")
        assert classify_amount(text, start, end) == "proviso_limit"

    def test_advance_appropriation(self):
        text = "$71,000,000,000, plus reimbursements, which shall become available on October 1, 2024"
        assert classify_amount(text, 0, 15) == "advance_appropriation"

    def test_addition_to_prior(self):
        text = "$15,072,388,000, which shall be in addition to funds previously appropriated under this heading"
        assert classify_amount(text, 0, 16) == "addition_to_prior"


class TestFindAmounts:
    def test_single_appropriation(self):
        text = "For acquisition and construction, $2,022,775,000, to remain available until September 30, 2028"
        result = find_amounts(text)
        assert len(result) == 1
        assert result[0] == (2022775000, "appropriation")

    def test_multiple_types(self):
        """Real pattern from Medical Services: advance appropriation + rescission."""
        text = (
            "For necessary expenses, $71,000,000,000, plus reimbursements, "
            "which shall become available on October 1, 2024, and shall remain "
            "available until September 30, 2025: Provided further, That of the "
            "$74,004,000,000 that became available on October 1, 2023, previously "
            "appropriated under this heading, $3,034,205,000 is hereby rescinded"
        )
        result = find_amounts(text)
        amounts = {(a, t) for a, t in result}
        assert (71000000000, "advance_appropriation") in amounts
        assert (3034205000, "rescission") in amounts

    def test_appropriation_with_proviso(self):
        text = (
            "For acquisition, $2,022,775,000, to remain available until "
            "September 30, 2028: Provided, That, of this amount, not to exceed "
            "$398,145,000 shall be available for study, planning, design"
        )
        result = find_amounts(text)
        amounts = {(a, t) for a, t in result}
        assert (2022775000, "appropriation") in amounts
        assert (398145000, "proviso_limit") in amounts


class TestExtractLineItems:
    def test_single_intermediate_with_amount(self):
        """An appropriations-intermediate element with header and text."""
        xml_str = """
        <appropriations-intermediate id="H7E3380D5B83C4D6FBF4DDF1136755C97">
            <header>Military construction, army</header>
            <text>For acquisition, construction, installation, and equipment
            of temporary or permanent public works, military installations,
            $2,022,775,000, to remain available until September 30, 2028</text>
        </appropriations-intermediate>
        """
        elem = ET.fromstring(xml_str)
        category = ("Division A: Military Construction", "Title I: DEPARTMENT OF DEFENSE")
        items = extract_line_items_from_element(elem, category)
        assert len(items) == 1
        item = items[0]
        assert item.amount == 2022775000
        assert item.amount_type == "appropriation"
        assert item.name == "Military construction, army"
        assert item.category == category
        assert item.element_id == "H7E3380D5B83C4D6FBF4DDF1136755C97"
        assert item.section_number == ""

    def test_element_without_text_produces_nothing(self):
        """Header-only elements produce no line items."""
        xml_str = """
        <appropriations-major id="H75F2C063BCC748679A69EBC2CFAD4650">
            <header>DEPARTMENT OF VETERANS AFFAIRS</header>
        </appropriations-major>
        """
        elem = ET.fromstring(xml_str)
        items = extract_line_items_from_element(elem, ("Division A",))
        assert items == []


class TestBuildCategory:
    def test_full_hierarchy(self):
        result = build_category(
            "Division A: Military Construction",
            "Title I: DEPARTMENT OF DEFENSE",
            "Administrative provisions",
            None,
        )
        assert result == (
            "Division A: Military Construction",
            "Title I: DEPARTMENT OF DEFENSE",
            "Administrative provisions",
        )

    def test_with_intermediate_no_major(self):
        """Intermediate without major gets an empty-string placeholder for major."""
        result = build_category(
            "Division A: Military Construction",
            "Title I: DEPARTMENT OF DEFENSE",
            None,
            "Military construction, army",
        )
        assert result == (
            "Division A: Military Construction",
            "Title I: DEPARTMENT OF DEFENSE",
            "",
            "Military construction, army",
        )

    def test_no_major_or_intermediate(self):
        result = build_category(
            "Division B: Agriculture",
            "Title I: AGRICULTURAL PROGRAMS",
            None,
            None,
        )
        assert result == (
            "Division B: Agriculture",
            "Title I: AGRICULTURAL PROGRAMS",
        )

    def test_all_levels(self):
        result = build_category(
            "Division A: Military Construction",
            "Title II: DEPARTMENT OF VETERANS AFFAIRS",
            "DEPARTMENT OF VETERANS AFFAIRS",
            "Veterans health administration",
        )
        assert result == (
            "Division A: Military Construction",
            "Title II: DEPARTMENT OF VETERANS AFFAIRS",
            "DEPARTMENT OF VETERANS AFFAIRS",
            "Veterans health administration",
        )


class TestParseTitle:
    def test_flat_sibling_context(self):
        """Major, intermediate, and small siblings get correct categories."""
        xml_str = """
        <title style="appropriations">
            <enum>I</enum>
            <appropriations-major id="M1">
                <header>DEPARTMENT OF DEFENSE</header>
            </appropriations-major>
            <appropriations-intermediate id="I1">
                <header>Military construction, army</header>
                <text>For acquisition, $2,022,775,000, to remain available</text>
            </appropriations-intermediate>
            <appropriations-intermediate id="I2">
                <header>Military construction, navy</header>
                <text>For acquisition, $5,531,369,000, to remain available</text>
            </appropriations-intermediate>
        </title>
        """
        elem = ET.fromstring(xml_str)
        items = parse_title(elem, "Division A: MilCon")
        assert len(items) >= 2
        army = [i for i in items if "army" in i.name.lower()]
        navy = [i for i in items if "navy" in i.name.lower()]
        assert len(army) >= 1
        assert army[0].amount == 2022775000
        assert army[0].category == (
            "Division A: MilCon",
            "Title I",
            "DEPARTMENT OF DEFENSE",
            "Military construction, army",
        )
        assert len(navy) >= 1
        assert navy[0].amount == 5531369000

    def test_major_resets_intermediate(self):
        """When a new major appears, intermediate context resets."""
        xml_str = """
        <title style="appropriations">
            <enum>II</enum>
            <appropriations-major id="M1">
                <header>AGENCY ONE</header>
            </appropriations-major>
            <appropriations-intermediate id="I1">
                <header>Bureau A</header>
                <text>For operations, $100,000,000</text>
            </appropriations-intermediate>
            <appropriations-major id="M2">
                <header>AGENCY TWO</header>
            </appropriations-major>
            <appropriations-intermediate id="I2">
                <header>Bureau B</header>
                <text>For operations, $200,000,000</text>
            </appropriations-intermediate>
        </title>
        """
        elem = ET.fromstring(xml_str)
        items = parse_title(elem, "Division X")
        bureau_a = [i for i in items if "Bureau A" in i.name]
        bureau_b = [i for i in items if "Bureau B" in i.name]
        assert bureau_a[0].category == ("Division X", "Title II", "AGENCY ONE", "Bureau A")
        assert bureau_b[0].category == ("Division X", "Title II", "AGENCY TWO", "Bureau B")

    def test_including_transfer_header(self):
        """Parenthetical headers use the previous sibling's name."""
        xml_str = """
        <title style="appropriations">
            <enum>I</enum>
            <appropriations-small id="S1">
                <header>COMPENSATION AND PENSIONS</header>
            </appropriations-small>
            <appropriations-small id="S2">
                <header>(INCLUDING TRANSFER OF FUNDS)</header>
                <text>For the payment of compensation benefits, $15,072,388,000</text>
            </appropriations-small>
        </title>
        """
        elem = ET.fromstring(xml_str)
        items = parse_title(elem, "Division A")
        assert len(items) >= 1
        assert items[0].name == "COMPENSATION AND PENSIONS"
        assert items[0].amount == 15072388000

    def test_section_with_additional_amount(self):
        """Sections with appropriation language are extracted."""
        xml_str = """
        <title style="appropriations">
            <enum>I</enum>
            <appropriations-intermediate id="I1">
                <header>Administrative provisions</header>
            </appropriations-intermediate>
            <section id="SEC124">
                <enum>124.</enum>
                <text>For an additional amount for Military Construction, Army, $8,214,000</text>
            </section>
        </title>
        """
        elem = ET.fromstring(xml_str)
        items = parse_title(elem, "Division A")
        assert len(items) >= 1
        sec_items = [i for i in items if i.section_number]
        assert len(sec_items) == 1
        assert sec_items[0].amount == 8214000
        assert sec_items[0].section_number == "Sec. 124"

    def test_section_without_appropriation_skipped(self):
        """Restriction sections without appropriation language are skipped."""
        xml_str = """
        <title style="appropriations">
            <enum>I</enum>
            <section id="SEC101">
                <enum>101.</enum>
                <text>None of the funds made available in this title shall be
                expended for payments under a cost-plus-a-fixed-fee contract
                where cost estimates exceed $25,000</text>
            </section>
        </title>
        """
        elem = ET.fromstring(xml_str)
        items = parse_title(elem, "Division A")
        assert len(items) == 0


class TestParseBill:
    def test_metadata_extraction(self, tmp_path):
        """parse_bill extracts congress, bill_type, bill_number, version from XML."""
        xml_str = """<?xml version="1.0"?>
        <bill bill-stage="Enrolled-Bill" bill-type="olc">
            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dublinCore>
                    <dc:title>HR 4366 ENR: Consolidated Appropriations Act, 2024</dc:title>
                </dublinCore>
            </metadata>
            <form>
                <congress>One Hundred Eighteenth Congress</congress>
                <legis-num>H. R. 4366</legis-num>
            </form>
            <legis-body style="OLC">
            </legis-body>
        </bill>
        """
        xml_file = tmp_path / "6_enrolled-bill.xml"
        xml_file.write_text(xml_str)
        result = parse_bill(xml_file)

        assert result.congress == 118
        assert result.bill_type == "hr"
        assert result.bill_number == 4366
        assert result.version == "enrolled-bill"
        assert result.items == []


ENROLLED_BILL_PATH = Path("output/118-hr-4366/6_enrolled-bill.xml")


class TestFullEnrolledBill:
    """Integration tests against the real enrolled bill XML."""

    def test_metadata(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        result = parse_bill(ENROLLED_BILL_PATH)
        assert result.congress == 118
        assert result.bill_type == "hr"
        assert result.bill_number == 4366
        assert result.version == "enrolled-bill"

    def test_extracts_many_items(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        result = parse_bill(ENROLLED_BILL_PATH)
        assert len(result.items) > 500

    def test_milcon_army_appropriation(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        result = parse_bill(ENROLLED_BILL_PATH)
        milcon_army = [
            i for i in result.items
            if i.name.lower() == "military construction, army"
            and i.amount_type == "appropriation"
            and i.amount == 2_022_775_000
        ]
        assert len(milcon_army) == 1

    def test_medical_services_advance_and_rescission(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        result = parse_bill(ENROLLED_BILL_PATH)
        med_svc = [i for i in result.items if "medical services" in i.name.lower()]
        amounts = {(i.amount, i.amount_type) for i in med_svc}
        assert (71_000_000_000, "advance_appropriation") in amounts
        assert (3_034_205_000, "rescission") in amounts

    def test_comp_pensions_addition_and_advance(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        result = parse_bill(ENROLLED_BILL_PATH)
        comp = [i for i in result.items if "compensation and pensions" in i.name.lower()]
        amounts = {(i.amount, i.amount_type) for i in comp}
        assert (15_072_388_000, "addition_to_prior") in amounts
        assert (182_310_515_000, "advance_appropriation") in amounts


class TestLineItemToRow:
    def test_full_category(self):
        item = LineItem(
            amount=2_022_775_000,
            amount_type="appropriation",
            name="Military construction, army",
            category=("Division A: MilCon", "Title I", "DEPT OF DEFENSE", "Military construction, army"),
            section_number="",
            element_id="H7E33",
            raw_text="For acquisition...",
        )
        bill = BillLineItems(congress=118, bill_type="hr", bill_number=4366, version="enrolled-bill", items=[item])
        row = line_item_to_row(item, bill)
        assert row["congress"] == 118
        assert row["bill_type"] == "hr"
        assert row["bill_number"] == 4366
        assert row["version"] == "enrolled-bill"
        assert row["division"] == "Division A: MilCon"
        assert row["title"] == "Title I"
        assert row["major"] == "DEPT OF DEFENSE"
        assert row["intermediate"] == "Military construction, army"
        assert row["name"] == "Military construction, army"
        assert row["amount"] == 2_022_775_000
        assert row["amount_type"] == "appropriation"
        assert row["element_id"] == "H7E33"
        assert set(row.keys()) == set(CSV_COLUMNS)

    def test_short_category(self):
        item = LineItem(
            amount=100_000,
            amount_type="appropriation",
            name="Some program",
            category=("Division B: Ag", "Title I"),
            section_number="",
            element_id="X1",
            raw_text="...",
        )
        bill = BillLineItems(congress=118, bill_type="hr", bill_number=1, version="introduced", items=[item])
        row = line_item_to_row(item, bill)
        assert row["major"] == ""
        assert row["intermediate"] == ""


class TestWriteCsv:
    def _make_bill(self, version="enrolled-bill", items=None):
        if items is None:
            items = [
                LineItem(
                    amount=100_000_000,
                    amount_type="appropriation",
                    name="Test Program",
                    category=("Division A", "Title I", "AGENCY", "Bureau"),
                    section_number="",
                    element_id="X1",
                    raw_text="...",
                ),
            ]
        return BillLineItems(congress=118, bill_type="hr", bill_number=4366, version=version, items=items)

    def test_single_bill(self):
        bill = self._make_bill()
        buf = io.StringIO()
        write_csv([bill], buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["name"] == "Test Program"
        assert rows[0]["amount"] == "100000000"
        assert rows[0]["version"] == "enrolled-bill"
        assert list(reader.fieldnames) == CSV_COLUMNS

    def test_multiple_bills(self):
        bill1 = self._make_bill(version="reported-in-house")
        bill2 = self._make_bill(version="enrolled-bill")
        buf = io.StringIO()
        write_csv([bill1, bill2], buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["version"] == "reported-in-house"
        assert rows[1]["version"] == "enrolled-bill"


class TestCli:
    def test_export_stdout(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        import subprocess

        result = subprocess.run(
            ["uv", "run", "python", "parse_bill.py", "export", str(ENROLLED_BILL_PATH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == ",".join(CSV_COLUMNS)
        assert len(lines) > 500  # header + many data rows

    def test_export_file(self, tmp_path):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        import subprocess

        out_file = tmp_path / "test_output.csv"
        result = subprocess.run(
            ["uv", "run", "python", "parse_bill.py", "export", str(ENROLLED_BILL_PATH), "-o", str(out_file)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert out_file.exists()
        with open(out_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 500
        assert rows[0]["congress"] == "118"

    def test_export_all(self, tmp_path):
        bill_dir = Path("output/118-hr-4366")
        if not bill_dir.exists():
            pytest.skip("Real XML files not available")
        import subprocess

        out_file = tmp_path / "all_versions.csv"
        result = subprocess.run(
            ["uv", "run", "python", "parse_bill.py", "export-all", str(bill_dir), "-o", str(out_file)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        with open(out_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        versions = {r["version"] for r in rows}
        assert len(versions) > 1  # multiple versions present


class TestExtractPrimaryAmounts:
    def test_single_amount(self):
        """One pre-proviso amount returns it as appropriation."""
        xml_str = """<text>For acquisition, $2,022,775,000, to remain available</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        assert result == [(2022775000, "appropriation")]

    def test_largest_wins(self):
        """Small incidentals before the main number are excluded."""
        xml_str = """<text>including not to exceed $2,250 for official reception
        and representation expenses, $520,000,000</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        assert result == [(520000000, "appropriation")]

    def test_skips_proviso_amounts(self):
        """Amounts inside proviso blocks are excluded."""
        xml_str = """<text>For acquisition, $331,572,000, to remain available:
        <proviso><italic>Provided,</italic></proviso> That, of the amount,
        not to exceed $14,646,000 shall be available for study</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        assert result == [(331572000, "appropriation")]

    def test_advance_appropriation(self):
        """Amount before 'shall become available on' tagged as advance."""
        xml_str = """<text>For necessary expenses, $71,000,000,000, plus
        reimbursements, which shall become available on October 1, 2024</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        assert result == [(71000000000, "advance_appropriation")]

    def test_addition_to_prior(self):
        """Amount before 'in addition to funds previously' tagged correctly."""
        xml_str = """<text>For payment of benefits, $15,072,388,000, which
        shall be in addition to funds previously appropriated under this
        heading</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        assert result == [(15072388000, "addition_to_prior")]

    def test_current_plus_advance(self):
        """VA-style: both current-year and advance amounts are returned."""
        xml_str = """<text>For payment of benefits, $15,072,388,000, which
        shall be in addition to funds previously appropriated under this
        heading that became available on October 1, 2023, to remain available
        until expended; and, in addition, $182,310,515,000, which shall
        become available on October 1, 2024, to remain available until
        expended</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        amounts = {(a, t) for a, t in result}
        assert (15072388000, "addition_to_prior") in amounts
        assert (182310515000, "advance_appropriation") in amounts
        assert len(result) == 2

    def test_no_amounts(self):
        """Element with no dollar amounts returns empty list."""
        xml_str = """<text>None of the funds made available shall be used</text>"""
        text_el = ET.fromstring(xml_str)
        result = extract_primary_amounts(text_el)
        assert result == []


class TestPrimaryOnlyCli:
    def test_primary_only_fewer_rows(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        import subprocess

        full = subprocess.run(
            ["uv", "run", "python", "parse_bill.py", "export", str(ENROLLED_BILL_PATH)],
            capture_output=True, text=True,
        )
        primary = subprocess.run(
            ["uv", "run", "python", "parse_bill.py", "export", str(ENROLLED_BILL_PATH), "--primary-only"],
            capture_output=True, text=True,
        )
        full_count = len(full.stdout.strip().split("\n"))
        primary_count = len(primary.stdout.strip().split("\n"))
        assert primary_count < full_count
        assert primary_count > 100  # still substantial

    def test_primary_only_spot_check(self):
        if not ENROLLED_BILL_PATH.exists():
            pytest.skip("Real XML file not available")
        result = parse_bill(ENROLLED_BILL_PATH, primary_only=True)

        # Military construction, army: 1 primary row at $2,022,775,000
        milcon = [i for i in result.items
                  if i.name.lower() == "military construction, army"
                  and i.amount == 2_022_775_000]
        assert len(milcon) == 1
        assert milcon[0].amount_type == "appropriation"

        # Air Force Reserve: 1 primary row (not 3)
        afr = [i for i in result.items
               if "air force reserve" in i.name.lower()
               and i.amount == 331_572_000]
        assert len(afr) == 1

        # Comp & Pensions: 2 rows (addition_to_prior + advance)
        comp = [i for i in result.items
                if "compensation and pensions" in i.name.lower()]
        comp_types = {i.amount_type for i in comp}
        assert "addition_to_prior" in comp_types
        assert "advance_appropriation" in comp_types

        # Medical Services: advance_appropriation
        med = [i for i in result.items
               if "medical services" in i.name.lower()
               and i.amount == 71_000_000_000]
        assert len(med) == 1
        assert med[0].amount_type == "advance_appropriation"
