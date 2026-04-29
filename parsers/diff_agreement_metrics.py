"""Pure metrics for measuring how closely a candidate ``BillDiff``
agrees with a ground-truth ``BillDiff`` on the same logical bill
versions.

Used by ``test_pdf_diff_consistency.py`` and ``scripts/diff_compare_probe.py``
to score PDF-vs-PDF diff output against XML-vs-XML diff output. The
question these metrics answer is the staffer's actual product question
-- "does the diff I see when I compare two PDFs of a bill match what
I'd see if I had the XML versions?" -- not the older parser-output
parity question.

Vacuous-case convention: when there's nothing to measure (zero counts
of a type on both sides, no financial nodes anywhere, no modified
sections in the reference), each metric returns the "agree" value
(0.0 for delta-style, 1.0 for ratio-style, 0.0 for error-style).
Callers can sanity-check the inputs separately if they want to flag
degenerate diffs.
"""

from __future__ import annotations

import math
from difflib import SequenceMatcher

from diff_bill import BillDiff, NodeDiff, extract_amounts


def _normalize(text: str) -> str:
    return " ".join(text.split())


def summary_count_delta(xml_diff: BillDiff, pdf_diff: BillDiff) -> dict[str, float]:
    """Per-type relative count error.

    For each ``t`` in ``("added", "removed", "modified")``, return
    ``abs(pdf_count - xml_count) / max(xml_count, 1)``. Lower is
    better. The ``max(..., 1)`` denominator yields a finite delta even
    when XML has zero of a type but PDF has some (the metric then
    reflects "how many spurious" relative to one reference unit).
    """
    out: dict[str, float] = {}
    for t in ("added", "removed", "modified"):
        xml_n = xml_diff.summary.get(t, 0)
        pdf_n = pdf_diff.summary.get(t, 0)
        out[t] = abs(pdf_n - xml_n) / max(xml_n, 1)
    return out


def _financial_totals(diff: BillDiff) -> tuple[int, int]:
    old_total = 0
    new_total = 0
    for c in diff.changes:
        if c.old_text:
            old_total += sum(extract_amounts(c.old_text))
        if c.new_text:
            new_total += sum(extract_amounts(c.new_text))
    return old_total, new_total


def _ratio_and_error(xml_val: int, pdf_val: int) -> tuple[float, float]:
    if xml_val == 0 and pdf_val == 0:
        return 1.0, 0.0
    if xml_val == 0:
        return math.inf, math.inf
    ratio = pdf_val / xml_val
    return ratio, abs(1.0 - ratio)


def financial_total_agreement(xml_diff: BillDiff, pdf_diff: BillDiff) -> dict[str, float]:
    """Aggregate dollar-total agreement across all NodeDiffs.

    Sums ``old_amounts`` and ``new_amounts`` from every NodeDiff that
    has financial content (``compute_financial_change`` returns non-None).
    Returns ``{xml_old_total, xml_new_total, pdf_old_total, pdf_new_total,
    old_ratio, new_ratio, old_abs_pct_error, new_abs_pct_error}``.

    Headline staffer-relevant metric: if the dollar totals match, the
    rendered diff report will show the same financial summary regardless
    of source format.
    """
    xml_old, xml_new = _financial_totals(xml_diff)
    pdf_old, pdf_new = _financial_totals(pdf_diff)
    old_ratio, old_err = _ratio_and_error(xml_old, pdf_old)
    new_ratio, new_err = _ratio_and_error(xml_new, pdf_new)
    return {
        "xml_old_total": xml_old,
        "xml_new_total": xml_new,
        "pdf_old_total": pdf_old,
        "pdf_new_total": pdf_new,
        "old_ratio": old_ratio,
        "new_ratio": new_ratio,
        "old_abs_pct_error": old_err,
        "new_abs_pct_error": new_err,
    }


def modified_section_overlap(
    xml_diff: BillDiff,
    pdf_diff: BillDiff,
    *,
    sim_threshold: float = 0.7,
) -> float:
    """Fraction of XML "modified" NodeDiffs that have a corresponding
    "modified" NodeDiff in the PDF diff with similar body text.

    Candidate pairing: a PDF NodeDiff is considered for a given XML
    NodeDiff if either ``match_path`` or ``section_number`` matches.
    The score for each XML node is ``max(SequenceMatcher.ratio())``
    on whitespace-normalized ``new_text`` across its candidates; the
    XML node counts as "covered" when that score >= ``sim_threshold``.

    Vacuous = 1.0 when XML diff has no modified sections.
    """
    xml_modified = [c for c in xml_diff.changes if c.change_type == "modified"]
    if not xml_modified:
        return 1.0

    pdf_modified = [c for c in pdf_diff.changes if c.change_type == "modified"]
    by_path: dict[tuple[str, ...], list[NodeDiff]] = {}
    by_secnum: dict[str, list[NodeDiff]] = {}
    for c in pdf_modified:
        by_path.setdefault(c.match_path, []).append(c)
        if c.section_number:
            by_secnum.setdefault(c.section_number, []).append(c)

    covered = 0
    for xml_c in xml_modified:
        candidates: list[NodeDiff] = []
        candidates.extend(by_path.get(xml_c.match_path, []))
        if xml_c.section_number:
            candidates.extend(by_secnum.get(xml_c.section_number, []))
        if not candidates:
            continue
        xml_text = _normalize(xml_c.new_text or "")
        if not xml_text:
            continue
        max_sim = max(SequenceMatcher(None, xml_text, _normalize(c.new_text or "")).ratio() for c in candidates)
        if max_sim >= sim_threshold:
            covered += 1
    return covered / len(xml_modified)


def unpair_rate(diff: BillDiff) -> float:
    """Fraction of nodes the diff couldn't pair across the two versions.

    For consecutive bill versions most sections are unchanged, so a
    high unpair rate signals parser noise -- the parser produced
    different structures for v1 and v2 and ``diff_bills`` couldn't
    match them. This is the gate metric for PDF-vs-PDF self-consistency
    (no XML truth required).

    Returned in ``[0.0, 1.0]``. ``0.0`` when nothing was unpaired (or
    when the diff is empty -- vacuous). ``1.0`` when nothing was paired.
    """
    s = diff.summary
    paired = s.get("modified", 0) + s.get("unchanged", 0) + s.get("moved", 0)
    unpaired = s.get("added", 0) + s.get("removed", 0)
    total = paired + unpaired
    return unpaired / total if total else 0.0


def change_type_jaccard(xml_diff: BillDiff, pdf_diff: BillDiff) -> float:
    """Jaccard similarity over ``(match_path, change_type)`` tuples.

    Quick sanity check on overall diff alignment. 1.0 = identical sets,
    0.0 = disjoint, ``len(intersection) / len(union)`` otherwise.
    Both-empty returns 1.0 (vacuous agreement).
    """
    xml_keys = {(c.match_path, c.change_type) for c in xml_diff.changes}
    pdf_keys = {(c.match_path, c.change_type) for c in pdf_diff.changes}
    union = xml_keys | pdf_keys
    if not union:
        return 1.0
    return len(xml_keys & pdf_keys) / len(union)
