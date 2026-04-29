"""Diagnostic: PDF-pair diff vs XML-pair diff agreement.

DEMOTED to diagnostic by Pivot 2 (April 2026). The product gate now
lives in ``test_pdf_self_consistency.py`` (does not require XML).
This file remains useful for development to localize *why* a self-
consistency failure happens — by comparing the PDF-pair diff against
the XML-pair diff (treating the latter as ground truth).

For each consecutive PDF/XML quadruple in the corpus -- meaning a bill
where versions ``v_n`` and ``v_{n+1}`` BOTH have a PDF and an XML on
disk -- compute:

- ``xml_diff = diff_bills(parse_xml(v_n), parse_xml(v_{n+1}))`` (truth)
- ``pdf_diff = diff_bills(parse_pdf(v_n), parse_pdf(v_{n+1}))`` (candidate)

and assert agreement on the staffer-relevant axes:

- ``summary_count_delta`` <= 0.30 per type (added / removed / modified)
- ``financial_total_agreement`` ``abs_pct_error`` <= 0.15 (each side)
- ``modified_section_overlap`` >= 0.50

These are aspirational floors that the deep-hierarchy emitter cannot
clear. After the shallow-emitter rebuild lands, the floors will be
re-pinned to numbers that the rebuild can clear at the diagnostic tier.

Skipped automatically when no quadruples are present locally.

Marker convention (matches ``test_parsers_parity.py``):

- ``slow`` keeps it out of the default ``pytest -m "not slow"`` fast
  suite.
- ``diagnostic`` lets CI exclude this from the product gate via
  ``pytest -m "slow and not diagnostic"`` while still letting devs
  run it on demand via ``pytest -m diagnostic``.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from diff_bill import diff_bills
from parsers import load_bill_tree
from parsers.diff_agreement_metrics import (
    financial_total_agreement,
    modified_section_overlap,
    summary_count_delta,
)

BILLS_DIR = Path(__file__).parent / "bills"

# Pinned floors. Do NOT lower or raise inside a Phase B commit; ratchet
# upward in a separate PR after the rebuild stabilizes.
SUMMARY_DELTA_CEIL = 0.30
FIN_PCT_ERROR_CEIL = 0.15
MODIFIED_OVERLAP_FLOOR = 0.50

# Match files like "1_reported-in-house" so we can pair consecutive
# versions inside a bill directory.
_VERSION_INDEX_RE = re.compile(r"^(\d+)_")


def _consecutive_quadruples() -> list[tuple[Path, Path, Path, Path]]:
    """Find consecutive (v_n_xml, v_n_pdf, v_n+1_xml, v_n+1_pdf) quadruples
    where all four files exist."""
    quadruples: list[tuple[Path, Path, Path, Path]] = []
    if not BILLS_DIR.exists():
        return quadruples
    for bill_dir in sorted(p for p in BILLS_DIR.iterdir() if p.is_dir()):
        # Group XMLs by their leading index.
        indexed: dict[int, Path] = {}
        for xml_path in sorted(bill_dir.glob("*.xml")):
            m = _VERSION_INDEX_RE.match(xml_path.stem)
            if not m:
                continue
            indexed[int(m.group(1))] = xml_path
        if len(indexed) < 2:
            continue
        sorted_indices = sorted(indexed)
        for i, j in zip(sorted_indices, sorted_indices[1:]):
            x1 = indexed[i]
            x2 = indexed[j]
            p1 = x1.with_suffix(".pdf")
            p2 = x2.with_suffix(".pdf")
            if x1.exists() and x2.exists() and p1.exists() and p2.exists():
                quadruples.append((x1, p1, x2, p2))
    return quadruples


_QUADRUPLES = _consecutive_quadruples()
_IDS = [f"{q[0].parent.name}/{q[0].stem}->{q[2].stem}" for q in _QUADRUPLES]


@pytest.mark.slow
@pytest.mark.diagnostic
@pytest.mark.skipif(not _QUADRUPLES, reason="No consecutive PDF/XML quadruples in bills/")
@pytest.mark.parametrize("v1_xml,v1_pdf,v2_xml,v2_pdf", _QUADRUPLES, ids=_IDS)
def test_pdf_diff_matches_xml_diff(v1_xml: Path, v1_pdf: Path, v2_xml: Path, v2_pdf: Path):
    xml_v1 = load_bill_tree(v1_xml)
    xml_v2 = load_bill_tree(v2_xml)
    if len(xml_v1.nodes) == 0 or len(xml_v2.nodes) == 0:
        pytest.skip(f"Empty XML reference tree (v1 nodes={len(xml_v1.nodes)}, v2={len(xml_v2.nodes)})")

    pdf_v1 = load_bill_tree(v1_pdf)
    pdf_v2 = load_bill_tree(v2_pdf)

    xml_diff = diff_bills(xml_v1, xml_v2)
    pdf_diff = diff_bills(pdf_v1, pdf_v2)

    failures: list[str] = []

    sd = summary_count_delta(xml_diff, pdf_diff)
    for t, val in sd.items():
        if val > SUMMARY_DELTA_CEIL:
            failures.append(f"summary_delta[{t}]={val:.3f} (ceil {SUMMARY_DELTA_CEIL})")

    fa = financial_total_agreement(xml_diff, pdf_diff)
    for side in ("old", "new"):
        err = fa[f"{side}_abs_pct_error"]
        if err > FIN_PCT_ERROR_CEIL or math.isinf(err):
            failures.append(f"financial_{side}_abs_pct_error={err} (ceil {FIN_PCT_ERROR_CEIL})")

    overlap = modified_section_overlap(xml_diff, pdf_diff)
    if overlap < MODIFIED_OVERLAP_FLOOR:
        failures.append(f"modified_section_overlap={overlap:.3f} (floor {MODIFIED_OVERLAP_FLOOR})")

    label = f"{v1_xml.parent.name}/{v1_xml.stem}->{v2_xml.stem}"
    assert not failures, f"{label}: " + "; ".join(failures)
