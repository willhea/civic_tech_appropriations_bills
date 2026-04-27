"""Pure metrics for measuring how closely two BillTrees align.

Used by the parity test harness to score PDF-parser output against
the XML ground truth. All functions are pure functions over
``BillTree``; no file IO, no PDFs.

Vacuous-case convention: when there's nothing to measure (empty
reference tree, no amounts in any node), each metric returns 1.0.
Callers should sanity-check the reference tree separately rather
than relying on the metric to flag a degenerate input.
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from bill_tree import BillNode, BillTree
from diff_bill import extract_amounts


def _index_by_match_path(tree: BillTree) -> dict[tuple[str, ...], BillNode]:
    return {n.match_path: n for n in tree.nodes}


def _normalize(text: str) -> str:
    return " ".join(text.split())


def match_path_recall(xml: BillTree, pdf: BillTree) -> float:
    """Fraction of XML match_paths that also appear in the PDF tree.

    Vacuously 1.0 when the XML tree is empty.
    """
    xml_paths = {n.match_path for n in xml.nodes}
    if not xml_paths:
        return 1.0
    pdf_paths = {n.match_path for n in pdf.nodes}
    return len(xml_paths & pdf_paths) / len(xml_paths)


def body_similarity_per_match(xml: BillTree, pdf: BillTree) -> dict[tuple[str, ...], float]:
    """SequenceMatcher ratio of body_text per match_path that appears in both.

    Whitespace is collapsed on both sides before comparison so that
    layout differences (line breaks, indentation) don't depress the score.
    """
    pdf_index = _index_by_match_path(pdf)
    out: dict[tuple[str, ...], float] = {}
    for n in xml.nodes:
        other = pdf_index.get(n.match_path)
        if other is None:
            continue
        a = _normalize(n.body_text)
        b = _normalize(other.body_text)
        out[n.match_path] = SequenceMatcher(None, a, b).ratio()
    return out


def financial_recall(xml: BillTree, pdf: BillTree) -> float:
    """Fraction of XML dollar amounts recovered by the PDF, averaged
    across nodes that have any amounts in the XML.

    Multiset semantics: $100 appearing twice in XML and once in PDF
    counts as 1/2 recall for that node. Nodes whose XML body contains
    no amounts are excluded from the average. Vacuously 1.0 when no
    XML node contains any amount.
    """
    pdf_index = _index_by_match_path(pdf)
    per_node: list[float] = []
    for n in xml.nodes:
        xml_amounts = extract_amounts(n.body_text)
        if not xml_amounts:
            continue
        other = pdf_index.get(n.match_path)
        pdf_amounts = extract_amounts(other.body_text) if other is not None else ()
        xml_counter = Counter(xml_amounts)
        pdf_counter = Counter(pdf_amounts)
        recovered = sum((xml_counter & pdf_counter).values())
        per_node.append(recovered / sum(xml_counter.values()))
    if not per_node:
        return 1.0
    return sum(per_node) / len(per_node)
