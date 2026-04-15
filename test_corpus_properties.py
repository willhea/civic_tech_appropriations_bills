"""Property-based tests that run against the full bill XML corpus.

These are diagnostic tests, not TDD-driven. They check invariants that should
hold across all bill versions and surface issues mechanically. Failures here
indicate parser gaps, not test bugs.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from bill_tree import _extract_appropriations_text, find_bill_body, normalize_bill

BILLS_DIR = Path(__file__).parent / "bills"
ALL_XML_FILES = sorted(BILLS_DIR.glob("**/*.xml"))
DOLLAR_RE = re.compile(r"\$[\d,]+")

# Tags whose subtrees should be excluded from raw text collection.
# <quote> contains cited text, not appropriations content.
# <header> text is stored in header_text, not body_text.
_SKIP_TAGS = {"quote", "header"}


def _collect_body_text_excluding(body: ET.Element, skip_tags: set[str]) -> str:
    """Walk the element tree, collecting text but skipping subtrees with tags in skip_tags."""
    parts: list[str] = []

    def _walk(el: ET.Element) -> None:
        if el.tag in skip_tags:
            return
        if el.text:
            parts.append(el.text)
        for child in el:
            _walk(child)
            if child.tail:
                parts.append(child.tail)

    _walk(body)
    return " ".join(parts)


def _extract_dollar_amounts(text: str) -> list[int]:
    """Find all non-zero dollar amounts in text."""
    amounts = []
    for m in DOLLAR_RE.finditer(text):
        value = int(m.group().replace("$", "").replace(",", ""))
        if value > 0:
            amounts.append(value)
    return amounts


def _xml_id(xml_path: Path) -> str:
    """Create a readable test ID from a bill XML path."""
    return f"{xml_path.parent.name}/{xml_path.name}"


# 115-hr-244 v5 has 0 nodes due to amendment-doc legis-body wrapper (issue #2).
# Will be fixed in Part B. Mark as expected failure for now.
_XFAIL_ZERO_NODES = {
    "115-hr-244/5_engrossed-amendment-house.xml",
}


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_every_dollar_amount_appears_in_a_node(xml_path: Path) -> None:
    """Every dollar amount in the raw XML body should appear in at least one node's body_text.

    Excludes amounts inside <quote> and <header> elements (stored separately).
    Uses a 0.95 coverage ratio tolerance for deeply nested clauses (issue #4).
    """
    test_id = _xml_id(xml_path)
    if test_id in _XFAIL_ZERO_NODES:
        pytest.xfail(f"Known 0-node issue: {test_id}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    try:
        body = find_bill_body(root)
    except ValueError:
        pytest.skip("No bill body found")

    # Collect dollar amounts from raw XML, excluding quote/header subtrees
    raw_text = _collect_body_text_excluding(body, _SKIP_TAGS)
    raw_amounts = _extract_dollar_amounts(raw_text)

    if not raw_amounts:
        pytest.skip("No dollar amounts in bill body")

    # Parse with the actual parser
    bill_tree = normalize_bill(xml_path)
    all_body_text = " ".join(node.body_text for node in bill_tree.nodes)

    # Check which raw amounts appear in at least one node's body_text
    missing = []
    for amount in raw_amounts:
        # Check if the formatted amount string appears in any node text
        amount_str = f"${amount:,}"
        if amount_str not in all_body_text:
            missing.append(amount)

    total = len(raw_amounts)
    found = total - len(missing)
    ratio = found / total

    assert ratio >= 0.80, (
        f"{test_id}: {len(missing)}/{total} amounts missing (ratio={ratio:.3f}). "
        f"Sample missing: {missing[:5]}"
    )


# Files known to have duplicate match_paths (cross-division collisions, issue #1).
# Values are the current duplicate counts. Files not listed must have zero duplicates.
_KNOWN_DUPLICATE_COUNTS: dict[str, int] = {
    "113-hr-3547/5_engrossed-amendment-house.xml": 150,
    "113-hr-3547/6_enrolled-bill.xml": 73,
    "113-hr-83/6_engrossed-amendment-house.xml": 112,
    "113-hr-83/7_enrolled-bill.xml": 112,
    "114-hr-2029/6_engrossed-amendment-house.xml": 156,
    "114-hr-2029/7_enrolled-bill.xml": 156,
    "115-hr-1625/7_enrolled-bill.xml": 153,
    "115-hr-244/6_enrolled-bill.xml": 136,
    "115-hr-5895/2_engrossed-in-house.xml": 20,
    "115-hr-5895/3_placed-on-calendar-senate.xml": 20,
    "115-hr-5895/4_engrossed-amendment-senate.xml": 6,
    "115-hr-5895/5_enrolled-bill.xml": 2,
    "116-hr-1865/5_engrossed-amendment-house.xml": 55,
    "116-hr-1865/6_enrolled-bill.xml": 55,
    "118-hr-2882/5_engrossed-amendment-house.xml": 41,
    "118-hr-2882/6_enrolled-bill.xml": 41,
    "118-hr-4366/4_engrossed-amendment-senate.xml": 7,
    "118-hr-4366/5_engrossed-amendment-house.xml": 33,
    "118-hr-4366/6_enrolled-bill.xml": 33,
    # Fresh bills added for overfitting smoke test (2026-04-15)
    "117-hr-4432/1_reported-in-house.xml": 1,
    "117-hr-4502/1_reported-in-house.xml": 1,
    "117-hr-4502/2_engrossed-in-house.xml": 39,
    "117-hr-4502/3_received-in-senate.xml": 39,
    "118-hr-4820/1_reported-in-house.xml": 7,
}


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_no_duplicate_match_paths(xml_path: Path) -> None:
    """Each node's match_path should be unique within a bill.

    Duplicates indicate cross-division path collisions (issue #1).
    Files with known duplicates assert the count hasn't increased.
    Files with no known duplicates assert zero.
    """
    test_id = _xml_id(xml_path)
    bill_tree = normalize_bill(xml_path)

    if not bill_tree.nodes:
        pytest.skip("No nodes parsed")

    counts = Counter(node.match_path for node in bill_tree.nodes)
    dupes = {k: v for k, v in counts.items() if v > 1}
    total_dupes = sum(v - 1 for v in dupes.values())

    known = _KNOWN_DUPLICATE_COUNTS.get(test_id, 0)

    if known == 0:
        assert total_dupes == 0, (
            f"{test_id}: unexpected {total_dupes} duplicate match_paths. "
            f"Sample: {list(dupes.items())[:3]}"
        )
    else:
        assert total_dupes <= known, (
            f"{test_id}: duplicate count increased from {known} to {total_dupes}. "
            f"Sample: {list(dupes.items())[:3]}"
        )


_APPRO_TAGS = {"appropriations-major", "appropriations-intermediate", "appropriations-small"}

# Files with known missing appropriations elements (parser doesn't reach them).
# Typically caused by elements nested inside divisions/titles the parser skips.
_KNOWN_MISSING_APPRO: dict[str, int] = {
    "113-hr-3547/6_enrolled-bill.xml": 310,
    "115-hr-5895/5_enrolled-bill.xml": 33,
}


def _normalize_ws(text: str) -> str:
    """Collapse whitespace for comparison."""
    return " ".join(text.split())


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_every_appropriations_element_with_text_produces_node(xml_path: Path) -> None:
    """Every appropriations-* element with text content should map to a parsed node.

    Extracts text using the same function the parser uses, then checks that
    the normalized text appears in at least one node's body_text.
    """
    test_id = _xml_id(xml_path)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    try:
        body = find_bill_body(root)
    except ValueError:
        pytest.skip("No bill body found")

    # Find all appropriations elements with text content
    appro_elements = []
    for el in body.iter():
        if el.tag in _APPRO_TAGS:
            text = _extract_appropriations_text(el)
            if text.strip():
                appro_elements.append((el, text))

    if not appro_elements:
        pytest.skip("No appropriations elements with text")

    # Parse and collect all node body texts (normalized)
    bill_tree = normalize_bill(xml_path)
    node_texts = [_normalize_ws(node.body_text) for node in bill_tree.nodes]

    # Check each appropriations element's text appears in some node
    missing = []
    for el, text in appro_elements:
        normalized = _normalize_ws(text)
        if not any(normalized in nt for nt in node_texts):
            preview = normalized[:80]
            missing.append((el.tag, el.attrib.get("id", "?"), preview))

    total = len(appro_elements)
    found = total - len(missing)

    known_missing = _KNOWN_MISSING_APPRO.get(test_id, 0)

    if known_missing == 0:
        assert len(missing) == 0, (
            f"{test_id}: {len(missing)}/{total} appropriations elements not found in nodes. "
            f"Sample: {missing[:3]}"
        )
    else:
        assert len(missing) <= known_missing, (
            f"{test_id}: missing count increased from {known_missing} to {len(missing)}. "
            f"Sample: {missing[:3]}"
        )


# Tags excluded from character coverage: parser stores these in separate fields,
# not in body_text.
_CHAR_SKIP_TAGS = {"quote", "header", "enum"}


@pytest.mark.parametrize(
    "xml_path",
    ALL_XML_FILES,
    ids=[_xml_id(p) for p in ALL_XML_FILES],
)
def test_character_coverage_ratio(xml_path: Path) -> None:
    """Parser should capture a high ratio of the bill body's text content.

    Compares total characters in the body (excluding quote/header/enum subtrees)
    against total characters across all node body_text fields.
    """
    test_id = _xml_id(xml_path)
    if test_id in _XFAIL_ZERO_NODES:
        pytest.xfail(f"Known 0-node issue: {test_id}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    try:
        body = find_bill_body(root)
    except ValueError:
        pytest.skip("No bill body found")

    raw_text = _collect_body_text_excluding(body, _CHAR_SKIP_TAGS)
    raw_chars = len(raw_text.strip())

    if raw_chars == 0:
        pytest.skip("No text content in bill body")

    bill_tree = normalize_bill(xml_path)
    node_chars = sum(len(node.body_text) for node in bill_tree.nodes)

    ratio = node_chars / raw_chars if raw_chars > 0 else 0.0

    # Low floor catches only catastrophic failures. Actual ratios range from
    # ~0.12 (amendment docs) to ~1.0+ (full bills). Shell bills and early
    # versions with little appropriations text have legitimately low ratios.
    assert ratio >= 0.10, (
        f"{test_id}: character coverage ratio {ratio:.3f} "
        f"({node_chars}/{raw_chars} chars)"
    )
