"""Product-gate test: PDF-pair self-consistency on consecutive bill versions.

For each consecutive PDF pair ``(v_n.pdf, v_{n+1}.pdf)`` in the local
corpus, parse both, run ``diff_bills`` between them, and assert that
the ``unpair_rate`` is at or below a pinned floor. The metric is
``(added + removed) / total``: in real consecutive bill versions
most sections are unchanged, so a high unpair rate is parser noise
(the parser produced different structures for v1 and v2 and the
matcher couldn't pair them).

This is the actual product question for the staffer use case: the
staffer drops two PDF drafts of a bill into the tool and gets a
diff out. If the parser is internally consistent across the two
PDFs, the diff lines up the same logical sections; if not, the
diff is full of false-positive added/removed pairs.

XML is not required for this gate -- staffers comparing private
drafts won't have it. ``test_pdf_diff_consistency.py`` (the
demoted XML-pair-as-truth diagnostic) is still useful for
localizing *why* a self-consistency failure happens but does not
gate.

Pinned floor (provisional): ``unpair_rate <= 0.15``. Set from the
single-bill calibration (``118-hr-8752/1->2`` measured at 0.122
on the shallow emitter) and the planning hypothesis that real
consecutive bill versions rarely add or remove >15% of sections.
A follow-up PR re-derives the floor from a full corpus probe; do
not move it inside the same PR that lands the parser changes.

Skipped automatically when no consecutive PDF pairs are present
locally (populate via ``scripts/fetch_pdfs_for_existing_xmls.py
--all``). Tiny bills with fewer than ``MIN_TOTAL_NODES`` total
nodes across the diff are skipped because the unpair rate is too
volatile at small denominators to gate. Omnibus pairs (either PDF
> ``OMNIBUS_BYTE_THRESHOLD``) are ``xfail``'d as a known
"major rewrite class" — the FY-omnibus enrolled-bill versions
genuinely add/remove sections in volume, and the parser
over-fragments them; they're addressed separately.

Marked ``slow``; excluded from default ``pytest -m "not slow"``
runs. Excluded from ``-m diagnostic`` so it stays in the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from diff_bill import diff_bills
from parsers import load_bill_tree
from parsers.diff_agreement_metrics import unpair_rate

BILLS_DIR = Path(__file__).parent / "bills"

# Pinned floor. Provisional; tighten in a follow-up PR after a corpus probe.
UNPAIR_RATE_FLOOR = 0.15

# Skip pairs where the diff has fewer than this many total nodes -- the rate
# is too volatile to gate at small denominators.
MIN_TOTAL_NODES = 10

# PDFs above this size are FY-omnibus bills (12 divisions, 2000+ pages).
# Mark these xfail rather than gate on them; their unpair characteristics
# differ from single-purpose appropriations bills.
OMNIBUS_BYTE_THRESHOLD = 4 * 1024 * 1024  # 4 MB

_VERSION_INDEX_RE = re.compile(r"^(\d+)_")


def _consecutive_pdf_pairs() -> list[tuple[Path, Path]]:
    """Find consecutive ``(v_n.pdf, v_{n+1}.pdf)`` pairs in each bill dir."""
    pairs: list[tuple[Path, Path]] = []
    if not BILLS_DIR.exists():
        return pairs
    for bill_dir in sorted(p for p in BILLS_DIR.iterdir() if p.is_dir()):
        indexed: dict[int, Path] = {}
        for pdf_path in sorted(bill_dir.glob("*.pdf")):
            m = _VERSION_INDEX_RE.match(pdf_path.stem)
            if not m:
                continue
            indexed[int(m.group(1))] = pdf_path
        sorted_indices = sorted(indexed)
        for i, j in zip(sorted_indices, sorted_indices[1:]):
            pairs.append((indexed[i], indexed[j]))
    return pairs


_PAIRS = _consecutive_pdf_pairs()
_IDS = [f"{p1.parent.name}/{p1.stem}->{p2.stem}" for p1, p2 in _PAIRS]


def _is_omnibus_pair(p1: Path, p2: Path) -> bool:
    return p1.stat().st_size > OMNIBUS_BYTE_THRESHOLD or p2.stat().st_size > OMNIBUS_BYTE_THRESHOLD


@pytest.mark.slow
@pytest.mark.skipif(not _PAIRS, reason="No consecutive PDF pairs in bills/")
@pytest.mark.parametrize("pdf_v1,pdf_v2", _PAIRS, ids=_IDS)
def test_pdf_diff_self_consistent(pdf_v1: Path, pdf_v2: Path, request: pytest.FixtureRequest):
    if _is_omnibus_pair(pdf_v1, pdf_v2):
        request.applymarker(
            pytest.mark.xfail(
                reason="Omnibus bill (>4MB PDF). Major-rewrite class -- "
                "shallow emitter over-fragments these. Tracked separately."
            )
        )

    tree1 = load_bill_tree(pdf_v1)
    tree2 = load_bill_tree(pdf_v2)

    diff = diff_bills(tree1, tree2)
    s = diff.summary
    total = s.get("added", 0) + s.get("removed", 0) + s.get("modified", 0) + s.get("unchanged", 0) + s.get("moved", 0)
    if total < MIN_TOTAL_NODES:
        pytest.skip(f"Tiny diff (total={total} < {MIN_TOTAL_NODES}); unpair rate too noisy to gate")

    rate = unpair_rate(diff)
    assert rate <= UNPAIR_RATE_FLOOR, f"unpair_rate={rate:.3f} (floor {UNPAIR_RATE_FLOOR}); summary={dict(s)}"
