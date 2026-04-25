"""Cross-format parity suite: XML vs PDF.

When the local ``bills/`` corpus contains both XML and PDF for a given
bill version, this suite parses both and asserts the resulting
``BillTree``s are equal field-by-field on every node. ``element_id`` is
excluded from the comparison because the PDF parser mints synthetic IDs
while XML uses Congress.gov's opaque IDs — diff matching uses
``match_path``, not ``element_id``.

Skipped automatically when no corpus is present locally.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bill_tree import BillNode, BillTree
from parsers import load_bill_tree

BILLS_DIR = Path(__file__).parent / "bills"


def _normalize_body(text: str) -> str:
    """Mirror what ``extract_text_content`` does so PDF/XML compare cleanly."""
    return " ".join(text.split())


def _node_signature(n: BillNode) -> tuple:
    return (
        tuple(n.match_path),
        tuple(n.display_path),
        n.tag,
        n.header_text,
        n.section_number,
        n.division_label,
        _normalize_body(n.body_text),
    )


def _matched_xml_pdf_pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    if not BILLS_DIR.exists():
        return pairs
    for xml_path in BILLS_DIR.glob("**/*.xml"):
        pdf_path = xml_path.with_suffix(".pdf")
        if pdf_path.exists():
            pairs.append((xml_path, pdf_path))
    return pairs


_PAIRS = _matched_xml_pdf_pairs()


@pytest.mark.slow
@pytest.mark.skipif(not _PAIRS, reason="No matched XML/PDF pairs in bills/")
@pytest.mark.parametrize("xml_path,pdf_path", _PAIRS, ids=lambda p: p.name)
def test_xml_pdf_parity(xml_path: Path, pdf_path: Path):
    xml_tree: BillTree = load_bill_tree(xml_path)
    pdf_tree: BillTree = load_bill_tree(pdf_path)

    assert xml_tree.congress == pdf_tree.congress
    assert xml_tree.bill_type == pdf_tree.bill_type
    assert xml_tree.bill_number == pdf_tree.bill_number

    xml_sigs = [_node_signature(n) for n in xml_tree.nodes]
    pdf_sigs = [_node_signature(n) for n in pdf_tree.nodes]
    assert xml_sigs == pdf_sigs, _diff_signatures(xml_sigs, pdf_sigs)


def _diff_signatures(a: list[tuple], b: list[tuple]) -> str:
    """Render a short diff message describing the first mismatch."""
    if len(a) != len(b):
        return f"node count differs: xml={len(a)} pdf={len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"first mismatch at node {i}:\n  xml: {x}\n  pdf: {y}"
    return "trees equal"


# Watermark fixture parity ------------------------------------------------


WATERMARK_FIXTURES = Path(__file__).parent / "test_data" / "watermarked"


def _watermark_pair() -> tuple[Path, Path] | None:
    """Return (clean_pdf, watermarked_pdf) if both exist, else None."""
    if not WATERMARK_FIXTURES.exists():
        return None
    clean = WATERMARK_FIXTURES / "clean.pdf"
    marked = WATERMARK_FIXTURES / "watermarked.pdf"
    if clean.exists() and marked.exists():
        return (clean, marked)
    return None


@pytest.mark.slow
@pytest.mark.skipif(_watermark_pair() is None, reason="No watermark fixture pair")
def test_watermarked_pdf_matches_clean_pdf():
    pair = _watermark_pair()
    assert pair is not None
    clean_path, marked_path = pair
    clean = load_bill_tree(clean_path)
    marked = load_bill_tree(marked_path)

    clean_sigs = [_node_signature(n) for n in clean.nodes]
    marked_sigs = [_node_signature(n) for n in marked.nodes]
    assert clean_sigs == marked_sigs, _diff_signatures(clean_sigs, marked_sigs)
    # No watermark text should leak into body_text.
    body = " ".join(n.body_text for n in marked.nodes)
    for word in ("DRAFT", "CONFIDENTIAL", "PRE-DECISIONAL"):
        assert not re.search(rf"\b{word}\b", body), f"watermark word {word!r} leaked into body_text"
