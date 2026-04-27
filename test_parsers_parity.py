"""Parity test harness: PDF parser output vs XML ground truth.

For each matched ``bills/<bill>/<idx>_<slug>.{pdf,xml}`` pair, parse
both and assert the PDF parse clears these PINNED baseline floors:

- ``match_path_recall >= 0.50`` — at least half the XML sections
  recovered.
- ``body_similarity_mean >= 0.70`` — average per-section body text
  similarity (whitespace-normalized SequenceMatcher ratio).
- ``financial_recall >= 0.80`` — at least 80% of dollar amounts
  recovered, multiset semantics.

These are the FLOOR the rebuild must clear, not the target. They
are deliberately not ratcheted inside the Phase B commits so each
commit's outcome is reproducible. A separate follow-up PR raises
them once the rebuild is stable.

Skipped automatically when no PDF/XML pairs are present locally
(populate via ``scripts/fetch_pdfs_for_existing_xmls.py --all``)
or when the dispatcher doesn't yet support PDFs (during Phase B
rebuild — once a PDF backend registers, the skips turn into real
runs).

Marked ``slow``; excluded from default ``pytest`` runs, run with
``-m slow``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers import UnsupportedFormatError, load_bill_tree
from parsers.parity_metrics import (
    body_similarity_per_match,
    financial_recall,
    match_path_recall,
)

BILLS_DIR = Path(__file__).parent / "bills"

# Pinned floors. Do NOT lower or raise inside a Phase B commit; ratchet
# upward in a separate PR after the rebuild stabilizes.
RECALL_FLOOR = 0.50
BODY_SIM_FLOOR = 0.70
FINANCIAL_FLOOR = 0.80


def _matched_pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    if not BILLS_DIR.exists():
        return pairs
    for xml_path in sorted(BILLS_DIR.glob("**/*.xml")):
        pdf_path = xml_path.with_suffix(".pdf")
        if pdf_path.exists():
            pairs.append((xml_path, pdf_path))
    return pairs


_PAIRS = _matched_pairs()
_IDS = [f"{x.parent.name}/{x.stem}" for x, _ in _PAIRS]


@pytest.mark.slow
@pytest.mark.skipif(not _PAIRS, reason="No matched XML/PDF pairs in bills/")
@pytest.mark.parametrize("xml_path,pdf_path", _PAIRS, ids=_IDS)
def test_pdf_meets_parity_floor(xml_path: Path, pdf_path: Path):
    xml_tree = load_bill_tree(xml_path)
    if len(xml_tree.nodes) == 0:
        # Some bills are stubs that ``normalize_bill`` walks down to zero
        # nodes (e.g. shell amendment vehicles). There's nothing to recall
        # against, so the parity question is N/A — not a PDF parser failure.
        pytest.skip(f"XML reference tree is empty (XML-side stub): {xml_path.name}")

    try:
        pdf_tree = load_bill_tree(pdf_path)
    except UnsupportedFormatError as e:
        pytest.skip(f"PDF backend not yet registered with load_bill_tree: {e}")

    recall = match_path_recall(xml_tree, pdf_tree)
    body_sims = body_similarity_per_match(xml_tree, pdf_tree)
    body_sim_mean = sum(body_sims.values()) / len(body_sims) if body_sims else 0.0
    fin_recall = financial_recall(xml_tree, pdf_tree)

    failures: list[str] = []
    if recall < RECALL_FLOOR:
        failures.append(f"match_path_recall={recall:.3f} (floor {RECALL_FLOOR})")
    if body_sim_mean < BODY_SIM_FLOOR:
        failures.append(f"body_similarity_mean={body_sim_mean:.3f} (floor {BODY_SIM_FLOOR})")
    if fin_recall < FINANCIAL_FLOOR:
        failures.append(f"financial_recall={fin_recall:.3f} (floor {FINANCIAL_FLOOR})")

    assert not failures, f"{pdf_path.name}: " + "; ".join(failures)
