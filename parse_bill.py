import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LineItem:
    """A single dollar amount extracted from an appropriations bill."""

    amount: int
    amount_type: str
    name: str
    category: tuple[str, ...]
    section_number: str
    element_id: str
    raw_text: str


@dataclass(frozen=True)
class BillLineItems:
    """All line items extracted from a single bill version."""

    congress: int
    bill_type: str
    bill_number: int
    version: str
    items: list[LineItem]


def parse_dollar_amount(text: str) -> int:
    """Parse a dollar string like '$1,234,567' to integer 1234567."""
    cleaned = text.replace("$", "").replace(",", "")
    return int(cleaned)


def classify_amount(text: str, match_start: int, match_end: int) -> str:
    """Classify a dollar amount based on surrounding context.

    Args:
        text: The full text containing the dollar amount.
        match_start: Start index of the dollar amount match in text.
        match_end: End index of the dollar amount match in text.

    Returns:
        One of: "appropriation", "rescission", "advance_appropriation",
        "proviso_limit", "addition_to_prior".
    """
    # Look at context window around the match
    before = text[max(0, match_start - 80):match_start].lower()
    after = text[match_end:match_end + 80].lower()

    if "rescind" in after or "rescind" in before:
        return "rescission"
    if "not to exceed" in before:
        return "proviso_limit"
    if "shall become available on" in after:
        return "advance_appropriation"
    if "in addition to funds previously" in after or "in addition to funds previously" in before:
        return "addition_to_prior"
    return "appropriation"


_DOLLAR_RE = re.compile(r"\$[\d,]+")


def find_amounts(text: str) -> list[tuple[int, str]]:
    """Find all dollar amounts in text and classify each one.

    Returns:
        List of (amount_int, amount_type) tuples.
    """
    results = []
    for match in _DOLLAR_RE.finditer(text):
        amount = parse_dollar_amount(match.group())
        amount_type = classify_amount(text, match.start(), match.end())
        results.append((amount, amount_type))
    return results


def extract_primary_amounts(text_element: ET.Element) -> list[tuple[int, str]]:
    """Extract primary allocation(s) from pre-proviso text.

    Uses a structural heuristic: only amounts appearing before the first
    <proviso> tag are considered. Of those, the largest is kept, plus any
    with advance_appropriation or addition_to_prior context.

    Returns:
        List of (amount, amount_type) tuples. Usually 1, sometimes 2+
        for accounts with current-year + advance appropriation patterns.
    """
    # Build pre-proviso text (everything before first <proviso>)
    pre_proviso = text_element.text or ""
    for child in text_element:
        if child.tag == "proviso":
            break
        pre_proviso += "".join(child.itertext()) + (child.tail or "")

    matches = list(_DOLLAR_RE.finditer(pre_proviso))
    if not matches:
        return []

    # Classify each amount and find the largest
    parsed = []
    for m in matches:
        value = parse_dollar_amount(m.group())
        after = " ".join(pre_proviso[m.end():m.end() + 120].split()).lower()

        if "shall become available on" in after:
            amount_type = "advance_appropriation"
        elif "in addition to funds previously" in after:
            amount_type = "addition_to_prior"
        else:
            amount_type = "appropriation"

        parsed.append((value, amount_type))

    largest_value = max(p[0] for p in parsed)

    # Keep the largest amount, plus any with special types
    return [
        (value, atype) for value, atype in parsed
        if value == largest_value or atype != "appropriation"
    ]


def build_category(
    division_label: str,
    title_label: str,
    major: str | None,
    intermediate: str | None,
) -> tuple[str, ...]:
    """Build a category tuple from the hierarchy levels.

    Args:
        division_label: Pre-formatted like "Division A: Military Construction".
        title_label: Pre-formatted like "Title I: DEPARTMENT OF DEFENSE".
        major: Major appropriation header text, or None.
        intermediate: Intermediate appropriation header text, or None.
    """
    parts = [division_label, title_label]
    if major:
        parts.append(major)
    if intermediate:
        parts.append(intermediate)
    return tuple(parts)


def extract_text_content(element: ET.Element) -> str:
    """Recursively extract all text content from an XML element."""
    return "".join(element.itertext())


def _get_header_text(element: ET.Element) -> str:
    """Get the header text from an appropriations element."""
    header = element.find("header")
    if header is not None:
        return extract_text_content(header).strip()
    return ""


def extract_line_items_from_element(
    element: ET.Element,
    category: tuple[str, ...],
    name_override: str | None = None,
    section_number: str = "",
    primary_only: bool = False,
) -> list[LineItem]:
    """Extract line items from an appropriations or section element.

    Args:
        element: An appropriations-* or section XML element.
        category: The hierarchy path tuple for this element.
        name_override: If set, use this instead of the element's header.
        section_number: The section number (e.g., "Sec. 124") if applicable.
        primary_only: If True, extract only primary allocations (pre-proviso).
    """
    name = name_override or _get_header_text(element)
    element_id = element.get("id", "")
    full_text = extract_text_content(element)

    if primary_only:
        text_el = element.find("text")
        amounts = extract_primary_amounts(text_el) if text_el is not None else []
    else:
        amounts = find_amounts(full_text)
    items = []
    for amount, amount_type in amounts:
        items.append(
            LineItem(
                amount=amount,
                amount_type=amount_type,
                name=name,
                category=category,
                section_number=section_number,
                element_id=element_id,
                raw_text=full_text,
            )
        )
    return items


_APPROPRIATION_TAGS = {
    "appropriations-major",
    "appropriations-intermediate",
    "appropriations-small",
}

_PARENTHETICAL_RE = re.compile(r"^\(.*\)$")

_APPROPRIATION_SECTION_PHRASES = (
    "for an additional amount",
    "for the cost of",
    "of the proceeds credited",
)


def _is_appropriation_section(section_element: ET.Element) -> bool:
    """Check if a section element contains appropriation language."""
    text_el = section_element.find("text")
    if text_el is None:
        return False
    text = extract_text_content(text_el).strip().lower()
    return any(text.startswith(phrase) for phrase in _APPROPRIATION_SECTION_PHRASES)


def parse_title(title_element: ET.Element, division_label: str, primary_only: bool = False) -> list[LineItem]:
    """Parse a <title> element, tracking flat-sibling context.

    Args:
        title_element: A <title> XML element containing appropriations children.
        division_label: Pre-formatted division label like "Division A: MilCon".

    Returns:
        All line items found within this title.
    """
    # Build title label from enum
    title_enum = title_element.find("enum")
    title_enum_text = title_enum.text.strip() if title_enum is not None else ""

    # Track context as we scan siblings
    current_major: str | None = None
    current_intermediate: str | None = None
    prev_name: str | None = None
    items: list[LineItem] = []

    title_label = f"Title {title_enum_text}"

    for child in title_element:
        tag = child.tag

        if tag == "appropriations-major":
            current_major = _get_header_text(child)
            current_intermediate = None
            prev_name = current_major
            text_el = child.find("text")
            if text_el is not None:
                category = build_category(division_label, title_label, current_major, None)
                items.extend(extract_line_items_from_element(child, category, primary_only=primary_only))

        elif tag == "appropriations-intermediate":
            current_intermediate = _get_header_text(child)
            header = current_intermediate
            if header and _PARENTHETICAL_RE.match(header):
                name_override = prev_name
            else:
                prev_name = header
                name_override = None

            text_el = child.find("text")
            if text_el is not None:
                category = build_category(division_label, title_label, current_major, current_intermediate)
                items.extend(extract_line_items_from_element(child, category, name_override=name_override, primary_only=primary_only))

        elif tag == "appropriations-small":
            header = _get_header_text(child)
            if header and _PARENTHETICAL_RE.match(header):
                name_override = prev_name
            else:
                if header:
                    prev_name = header
                name_override = None

            text_el = child.find("text")
            if text_el is not None:
                category = build_category(division_label, title_label, current_major, current_intermediate)
                items.extend(extract_line_items_from_element(child, category, name_override=name_override, primary_only=primary_only))

        elif tag == "section":
            enum_el = child.find("enum")
            section_num = f"Sec. {enum_el.text.strip()}" if enum_el is not None and enum_el.text else ""
            if _is_appropriation_section(child):
                category = build_category(division_label, title_label, current_major, current_intermediate)
                items.extend(extract_line_items_from_element(child, category, section_number=section_num, primary_only=primary_only))

    return items


_CONGRESS_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
}

_LEGIS_NUM_RE = re.compile(r"([A-Z])\.\s*(?:[A-Z]*\.?\s*)?(\d+)")


def parse_bill(xml_path: Path, primary_only: bool = False) -> BillLineItems:
    """Parse an appropriations bill XML file into structured line items.

    Args:
        xml_path: Path to the bill XML file.
        primary_only: If True, extract only primary allocations (pre-proviso).

    Returns:
        BillLineItems with metadata and all extracted line items.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Extract metadata
    congress = 0
    congress_el = root.find(".//congress")
    if congress_el is not None and congress_el.text:
        congress_text = congress_el.text.strip().lower()
        # Parse "One Hundred Eighteenth Congress" -> 118
        for word, num in _CONGRESS_WORDS.items():
            if word in congress_text:
                if "hundred" in congress_text:
                    congress = 100 + num
                else:
                    congress = num
                break

    bill_type = ""
    bill_number = 0
    legis_num_el = root.find(".//legis-num")
    if legis_num_el is not None and legis_num_el.text:
        match = _LEGIS_NUM_RE.search(legis_num_el.text.strip())
        if match:
            bill_type = match.group(1).lower()
            if bill_type == "h":
                bill_type = "hr"
            bill_number = int(match.group(2))

    # Extract version from filename
    version = ""
    stem = xml_path.stem
    parts = stem.split("_", 1)
    if len(parts) == 2:
        version = parts[1]

    # Parse all divisions and their titles
    all_items: list[LineItem] = []
    for division in root.iter("division"):
        div_enum = division.find("enum")
        div_header = division.find("header")
        div_enum_text = div_enum.text.strip() if div_enum is not None and div_enum.text else ""
        div_header_text = extract_text_content(div_header).strip() if div_header is not None else ""
        division_label = f"Division {div_enum_text}: {div_header_text}" if div_header_text else f"Division {div_enum_text}"

        for title in division.iter("title"):
            all_items.extend(parse_title(title, division_label, primary_only=primary_only))

    return BillLineItems(
        congress=congress,
        bill_type=bill_type,
        bill_number=bill_number,
        version=version,
        items=all_items,
    )


# --- CSV Export ---

CSV_COLUMNS = [
    "congress", "bill_type", "bill_number", "version",
    "division", "title", "major", "intermediate",
    "name", "amount", "amount_type", "section_number", "element_id",
]


def line_item_to_row(item: LineItem, bill: BillLineItems) -> dict:
    """Convert a LineItem to a flat dict for CSV output."""
    cat = item.category
    return {
        "congress": bill.congress,
        "bill_type": bill.bill_type,
        "bill_number": bill.bill_number,
        "version": bill.version,
        "division": cat[0] if len(cat) > 0 else "",
        "title": cat[1] if len(cat) > 1 else "",
        "major": cat[2] if len(cat) > 2 else "",
        "intermediate": cat[3] if len(cat) > 3 else "",
        "name": item.name,
        "amount": item.amount,
        "amount_type": item.amount_type,
        "section_number": item.section_number,
        "element_id": item.element_id,
    }


def write_csv(bills: list[BillLineItems], output) -> None:
    """Write line items from one or more bill versions to CSV.

    Args:
        bills: List of parsed bill versions.
        output: File-like object to write to (e.g., sys.stdout or open file).
    """
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for bill in bills:
        for item in bill.items:
            writer.writerow(line_item_to_row(item, bill))


# --- CLI ---


def cmd_export(args: argparse.Namespace) -> None:
    xml_path = Path(args.xml_file)
    bill = parse_bill(xml_path, primary_only=args.primary_only)
    if args.output:
        with open(args.output, "w", newline="") as f:
            write_csv([bill], f)
    else:
        write_csv([bill], sys.stdout)


def cmd_export_all(args: argparse.Namespace) -> None:
    directory = Path(args.directory)
    xml_files = sorted(directory.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {directory}", file=sys.stderr)
        sys.exit(1)
    bills = [parse_bill(f, primary_only=args.primary_only) for f in xml_files]
    if args.output:
        with open(args.output, "w", newline="") as f:
            write_csv(bills, f)
    else:
        write_csv(bills, sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse appropriations bill XML and export financial line items."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export a single bill version to CSV")
    export_parser.add_argument("xml_file", help="Path to bill XML file")
    export_parser.add_argument("-o", "--output", help="Output CSV file (default: stdout)")
    export_parser.add_argument("--primary-only", action="store_true",
                               help="Extract only primary allocations (exclude sub-allocations in provisos)")

    export_all_parser = subparsers.add_parser("export-all", help="Export all versions in a directory to CSV")
    export_all_parser.add_argument("directory", help="Directory containing bill XML files")
    export_all_parser.add_argument("-o", "--output", help="Output CSV file (default: stdout)")
    export_all_parser.add_argument("--primary-only", action="store_true",
                                   help="Extract only primary allocations (exclude sub-allocations in provisos)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "export":
        cmd_export(args)
    elif args.command == "export-all":
        cmd_export_all(args)


if __name__ == "__main__":
    main()