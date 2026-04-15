"""Normalize bill XML into a structured tree of content nodes."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BillNode:
    """A single content-bearing node from a bill XML."""

    match_path: tuple[str, ...]
    display_path: tuple[str, ...]
    tag: str
    element_id: str
    header_text: str
    body_text: str
    section_number: str


@dataclass(frozen=True)
class BillTree:
    """Normalized representation of one bill version."""

    congress: int
    bill_type: str
    bill_number: int
    version: str
    nodes: list[BillNode]


def normalize_header(text: str) -> str:
    """Normalize a header for matching: lowercase, collapse whitespace."""
    return " ".join(text.lower().split())


def find_bill_body(root: ET.Element) -> ET.Element:
    """Find the effective body element from a bill or amendment-doc root.

    Returns legis-body for bills, or amendment-block for amendment-docs.
    Raises ValueError if no body can be found.
    """
    # Standard bill: <bill><legis-body>
    body = root.find("legis-body")
    if body is not None:
        return body

    # Amendment doc: <amendment-doc><engrossed-amendment-body><amendment><amendment-block>
    block = root.find(".//engrossed-amendment-body/amendment/amendment-block")
    if block is not None:
        return block

    raise ValueError("Could not find bill body in XML")


_LIST_MARKER_RE = re.compile(r" (?=\((?:[0-9]{1,2}|[a-z]{1,4}|[A-Z])\))")


def extract_text_content(element: ET.Element) -> str:
    """Recursively extract all text content from an XML element.

    Collapses runs of whitespace into single spaces and removes spaces
    before parenthetical list markers like (1), (A), (iv) so that
    formatting differences between bill versions don't appear as
    textual changes.
    """
    text = " ".join("".join(element.itertext()).split())
    return _LIST_MARKER_RE.sub("", text)


def get_header_text(element: ET.Element) -> str:
    """Get the header text from an element."""
    header = element.find("header")
    if header is not None:
        return extract_text_content(header).strip()
    return ""


_PARENTHETICAL_RE = re.compile(r"^\(.*\)$")

_CONGRESS_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20,
}

_LEGIS_NUM_RE = re.compile(r"([A-Z])\.\s*(?:[A-Z]*\.?\s*)?(\d+)")


def _build_paths(
    title_header: str,
    division_label: str,
    major: str | None,
    intermediate: str | None,
    leaf_header: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Build match_path and display_path tuples.

    match_path: normalized, no division. Used for cross-version matching.
    display_path: original case, includes division. Used for human display.
    """
    match_parts: list[str] = []
    display_parts: list[str] = []

    if division_label:
        display_parts.append(division_label)

    if title_header:
        match_parts.append(normalize_header(title_header))
        display_parts.append(title_header)

    if major:
        match_parts.append(normalize_header(major))
        display_parts.append(major)

    if intermediate:
        match_parts.append(normalize_header(intermediate))
        display_parts.append(intermediate)

    if leaf_header and leaf_header != major and leaf_header != intermediate:
        match_parts.append(normalize_header(leaf_header))
        display_parts.append(leaf_header)

    return tuple(match_parts), tuple(display_parts)


def walk_title(
    title_element: ET.Element,
    title_header: str,
    division_label: str,
) -> list[BillNode]:
    """Walk a <title> element, tracking flat-sibling context.

    Produces BillNodes for every content-bearing element (has a <text> child).
    Tracks major/intermediate context as it scans siblings.

    Args:
        title_element: A <title> XML element.
        title_header: The title's header text (may be empty for headerless titles).
        division_label: Division label for display_path (empty if no division).
    """
    current_major: str | None = None
    current_intermediate: str | None = None
    prev_name: str | None = None
    nodes: list[BillNode] = []

    for child in title_element:
        tag = child.tag

        if tag == "appropriations-major":
            current_major = get_header_text(child)
            current_intermediate = None
            prev_name = current_major

            text_el = child.find("text")
            if text_el is not None:
                match_path, display_path = _build_paths(
                    title_header, division_label, current_major, None, None,
                )
                nodes.append(BillNode(
                    match_path=match_path,
                    display_path=display_path,
                    tag=tag,
                    element_id=child.attrib.get("id", ""),
                    header_text=current_major or "",
                    body_text=extract_text_content(text_el),

                    section_number="",
                ))

        elif tag == "appropriations-intermediate":
            header = get_header_text(child)
            current_intermediate = header

            if header and _PARENTHETICAL_RE.match(header):
                effective_header = prev_name
            else:
                prev_name = header
                effective_header = header

            text_el = child.find("text")
            if text_el is not None:
                match_path, display_path = _build_paths(
                    title_header, division_label, current_major, effective_header, None,
                )
                nodes.append(BillNode(
                    match_path=match_path,
                    display_path=display_path,
                    tag=tag,
                    element_id=child.attrib.get("id", ""),
                    header_text=header,
                    body_text=extract_text_content(text_el),

                    section_number="",
                ))

        elif tag == "appropriations-small":
            header = get_header_text(child)

            if header and _PARENTHETICAL_RE.match(header):
                effective_header = prev_name
            else:
                if header:
                    prev_name = header
                effective_header = header

            text_el = child.find("text")
            if text_el is not None:
                match_path, display_path = _build_paths(
                    title_header, division_label, current_major, current_intermediate, effective_header,
                )
                nodes.append(BillNode(
                    match_path=match_path,
                    display_path=display_path,
                    tag=tag,
                    element_id=child.attrib.get("id", ""),
                    header_text=header or "",
                    body_text=extract_text_content(text_el),

                    section_number="",
                ))

        elif tag == "section":
            enum_el = child.find("enum")
            section_num = ""
            if enum_el is not None and enum_el.text:
                section_num = f"Sec. {enum_el.text.strip().rstrip('.')}"

            body_text = _extract_section_text(child)
            if body_text:
                sec_label = section_num.lower() if section_num else ""
                match_path, display_path = _build_paths(
                    title_header, division_label, current_major, current_intermediate, sec_label,
                )
                nodes.append(BillNode(
                    match_path=match_path,
                    display_path=display_path,
                    tag=tag,
                    element_id=child.attrib.get("id", ""),
                    header_text=get_header_text(child),
                    body_text=body_text,

                    section_number=section_num,
                ))

    return nodes


def _extract_appropriations_text(element: ET.Element) -> str:
    """Extract all text content from an appropriations element.

    Captures text from all children except <enum> and <header>,
    including direct <text> children and <paragraph> children.
    Returns empty string if no text content found.
    """
    parts = []
    for child in element:
        if child.tag in ("enum", "header"):
            continue
        parts.append(extract_text_content(child))
    return " ".join(part for part in parts if part).strip()


def _extract_section_text(section: ET.Element) -> str:
    """Extract text from a section element.

    If the section has a direct <text> child, use that.
    Otherwise, extract all text recursively from the section
    (excluding the enum and header), which captures subsections.
    Returns empty string if no text content found.
    """
    text_el = section.find("text")
    if text_el is not None:
        return extract_text_content(text_el)

    # No direct <text> child. Check for subsections or other nested content.
    # Extract text from everything except enum and header.
    parts = []
    for child in section:
        if child.tag in ("enum", "header"):
            continue
        parts.append(extract_text_content(child))
    text = "".join(parts).strip()
    return text


def walk_body_sections(body: ET.Element) -> list[BillNode]:
    """Walk sections directly under a body element (no titles).

    Used for simple bills like HR 2882 v1-3 where the structure is
    just legis-body > section with no title or division wrappers.
    """
    nodes: list[BillNode] = []

    for child in body:
        if child.tag != "section":
            continue

        body_text = _extract_section_text(child)
        if not body_text:
            continue

        enum_el = child.find("enum")
        section_num = ""
        if enum_el is not None and enum_el.text:
            section_num = f"Sec. {enum_el.text.strip().rstrip('.')}"

        sec_label = section_num.lower() if section_num else ""
        match_path = (sec_label,) if sec_label else ()
        display_path = (section_num,) if section_num else ()

        nodes.append(BillNode(
            match_path=match_path,
            display_path=display_path,
            tag="section",
            element_id=child.attrib.get("id", ""),
            header_text=get_header_text(child),
            body_text=body_text,
            section_number=section_num,
        ))

    return nodes


def _extract_metadata(root: ET.Element, xml_path: Path) -> tuple[int, str, int, str]:
    """Extract congress, bill_type, bill_number, version from XML root and filename."""
    congress = 0
    congress_el = root.find(".//congress")
    if congress_el is not None and congress_el.text:
        congress_text = congress_el.text.strip().lower()
        # Try numeric first (e.g., "118th CONGRESS")
        num_match = re.search(r"(\d+)", congress_text)
        if num_match:
            congress = int(num_match.group(1))
        else:
            # Try word form (e.g., "One Hundred Eighteenth Congress")
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

    version = ""
    stem = xml_path.stem
    parts = stem.split("_", 1)
    if len(parts) == 2:
        version = parts[1]

    return congress, bill_type, bill_number, version


def normalize_bill(xml_path: Path) -> BillTree:
    """Parse a bill XML file into a normalized BillTree.

    Handles three structural shapes:
    - With divisions: body > division > title > appropriations-*
    - Without divisions, with titles: body > title > appropriations-*
    - Without titles: body > section (simple bills)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    body = find_bill_body(root)
    congress, bill_type, bill_number, version = _extract_metadata(root, xml_path)

    all_nodes: list[BillNode] = []

    # Check for divisions first
    divisions = body.findall("division")
    if divisions:
        for div in divisions:
            div_enum = div.find("enum")
            div_header = div.find("header")
            div_enum_text = div_enum.text.strip() if div_enum is not None and div_enum.text else ""
            div_header_text = extract_text_content(div_header).strip() if div_header is not None else ""
            if div_header_text:
                division_label = f"Division {div_enum_text}: {div_header_text}"
            else:
                division_label = f"Division {div_enum_text}"

            for title in div.findall("title"):
                title_header = get_header_text(title)
                all_nodes.extend(walk_title(title, title_header, division_label))
        return BillTree(congress, bill_type, bill_number, version, all_nodes)

    # Check for titles directly under body
    titles = body.findall("title")
    if titles:
        for title in titles:
            title_header = get_header_text(title)
            all_nodes.extend(walk_title(title, title_header, ""))
        return BillTree(congress, bill_type, bill_number, version, all_nodes)

    # Fallback: sections directly under body
    all_nodes = walk_body_sections(body)
    return BillTree(congress, bill_type, bill_number, version, all_nodes)
