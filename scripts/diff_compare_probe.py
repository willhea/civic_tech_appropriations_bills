"""Run the diff-agreement metrics across the full local corpus.

For each consecutive (v_n, v_{n+1}) pair where all four files
(v_n.xml, v_n.pdf, v_{n+1}.xml, v_{n+1}.pdf) exist:

1. Build ``xml_diff = diff_bills(parse_xml(v_n), parse_xml(v_{n+1}))``
2. Build ``pdf_diff = diff_bills(parse_pdf(v_n), parse_pdf(v_{n+1}))``
3. Score the agreement via the four metrics in
   :mod:`parsers.diff_agreement_metrics`.

Per-pair line is flushed live so progress is visible while large
omnibus bills parse. Aggregate stats land at the end.

Run::

    uv run python scripts/diff_compare_probe.py
"""

from __future__ import annotations

import math
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from diff_bill import diff_bills  # noqa: E402
from parsers import load_bill_tree  # noqa: E402
from parsers.diff_agreement_metrics import (  # noqa: E402
    change_type_jaccard,
    financial_total_agreement,
    modified_section_overlap,
    summary_count_delta,
)

BILLS_DIR = _REPO_ROOT / "bills"
_VERSION_INDEX_RE = re.compile(r"^(\d+)_")


def _consecutive_quadruples() -> list[tuple[Path, Path, Path, Path]]:
    quadruples: list[tuple[Path, Path, Path, Path]] = []
    if not BILLS_DIR.exists():
        return quadruples
    for bill_dir in sorted(p for p in BILLS_DIR.iterdir() if p.is_dir()):
        indexed: dict[int, Path] = {}
        for xml_path in sorted(bill_dir.glob("*.xml")):
            m = _VERSION_INDEX_RE.match(xml_path.stem)
            if not m:
                continue
            indexed[int(m.group(1))] = xml_path
        sorted_indices = sorted(indexed)
        for i, j in zip(sorted_indices, sorted_indices[1:]):
            x1 = indexed[i]
            x2 = indexed[j]
            p1 = x1.with_suffix(".pdf")
            p2 = x2.with_suffix(".pdf")
            if p1.exists() and p2.exists():
                quadruples.append((x1, p1, x2, p2))
    return quadruples


def _fmt(val: float) -> str:
    if math.isinf(val):
        return "  inf "
    return f"{val:6.3f}"


def _score_quadruple(quad: tuple[Path, Path, Path, Path]) -> dict:
    """Worker: load 4 trees, compute the 4 metrics. Pickle-safe."""
    v1_xml, v1_pdf, v2_xml, v2_pdf = quad
    label = f"{v1_xml.parent.name}/{v1_xml.stem}->{v2_xml.stem}"
    t0 = time.time()
    try:
        xml_v1 = load_bill_tree(v1_xml)
        xml_v2 = load_bill_tree(v2_xml)
        if len(xml_v1.nodes) == 0 or len(xml_v2.nodes) == 0:
            return {"label": label, "status": "skipped", "elapsed": time.time() - t0}
        pdf_v1 = load_bill_tree(v1_pdf)
        pdf_v2 = load_bill_tree(v2_pdf)

        xml_diff = diff_bills(xml_v1, xml_v2)
        pdf_diff = diff_bills(pdf_v1, pdf_v2)

        sd = summary_count_delta(xml_diff, pdf_diff)
        fa = financial_total_agreement(xml_diff, pdf_diff)
        ov = modified_section_overlap(xml_diff, pdf_diff)
        jc = change_type_jaccard(xml_diff, pdf_diff)
        return {
            "label": label,
            "status": "ok",
            "elapsed": time.time() - t0,
            "delta_added": sd["added"],
            "delta_removed": sd["removed"],
            "delta_modified": sd["modified"],
            "fin_old_err": fa["old_abs_pct_error"],
            "fin_new_err": fa["new_abs_pct_error"],
            "modified_overlap": ov,
            "jaccard": jc,
        }
    except Exception as e:  # noqa: BLE001
        return {"label": label, "status": "error", "error": str(e), "elapsed": time.time() - t0}


def main() -> None:
    quads = _consecutive_quadruples()
    workers = int(os.environ.get("PROBE_WORKERS", os.cpu_count() or 4))
    print(f"Quadruples: {len(quads)} (workers: {workers})", flush=True)
    print(
        f"{'Bill / Pair':55s} {'Δadd':>6s} {'Δrem':>6s} {'Δmod':>6s} "
        f"{'FinOldErr':>10s} {'FinNewErr':>10s} {'OvMod':>6s} {'Jacc':>6s} {'Time':>6s}",
        flush=True,
    )
    print("-" * 130, flush=True)

    rows: list[dict[str, float]] = []
    skipped = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_label = {executor.submit(_score_quadruple, q): q for q in quads}
        for future in as_completed(future_to_label):
            r = future.result()
            label = r["label"]
            elapsed = r["elapsed"]
            if r["status"] == "skipped":
                skipped += 1
                print(f"{label:55s} (empty XML — skipped) {elapsed:5.1f}s", flush=True)
                continue
            if r["status"] == "error":
                errors += 1
                print(f"{label:55s} ERROR: {r['error']} ({elapsed:5.1f}s)", flush=True)
                continue
            rows.append(r)
            print(
                f"{label:55s} {_fmt(r['delta_added'])} {_fmt(r['delta_removed'])} {_fmt(r['delta_modified'])} "
                f"{_fmt(r['fin_old_err']):>10s} {_fmt(r['fin_new_err']):>10s} "
                f"{_fmt(r['modified_overlap'])} {_fmt(r['jaccard'])} {elapsed:5.1f}s",
                flush=True,
            )

    print("-" * 130, flush=True)
    print(f"Skipped (empty XML): {skipped}", flush=True)
    print(f"Errors: {errors}", flush=True)
    print(flush=True)

    if not rows:
        return

    n = len(rows)

    def avg(key: str, finite_only: bool = False) -> float:
        vals = [r[key] for r in rows]
        if finite_only:
            vals = [v for v in vals if math.isfinite(v)]
        return sum(vals) / len(vals) if vals else 0.0

    print(f"Aggregate over {n} non-skipped pairs:")
    print(
        f"  avg summary delta:   added={avg('delta_added'):.3f}  "
        f"removed={avg('delta_removed'):.3f}  modified={avg('delta_modified'):.3f}  "
        f"(ceil 0.30)"
    )
    print(
        f"  avg fin abs % error: old={avg('fin_old_err', finite_only=True):.3f}  "
        f"new={avg('fin_new_err', finite_only=True):.3f}  (ceil 0.15, inf excluded from mean)"
    )
    print(f"  avg modified overlap: {avg('modified_overlap'):.3f}  (floor 0.50)")
    print(f"  avg change_type Jaccard: {avg('jaccard'):.3f}")

    above_sd = sum(
        1 for r in rows if r["delta_added"] <= 0.30 and r["delta_removed"] <= 0.30 and r["delta_modified"] <= 0.30
    )
    above_fin = sum(
        1
        for r in rows
        if math.isfinite(r["fin_old_err"])
        and math.isfinite(r["fin_new_err"])
        and r["fin_old_err"] <= 0.15
        and r["fin_new_err"] <= 0.15
    )
    above_ov = sum(1 for r in rows if r["modified_overlap"] >= 0.50)
    print(
        f"  pairs above floor: summary {above_sd}/{n} ({above_sd * 100 / n:.0f}%), "
        f"fin {above_fin}/{n} ({above_fin * 100 / n:.0f}%), "
        f"overlap {above_ov}/{n} ({above_ov * 100 / n:.0f}%)"
    )


if __name__ == "__main__":
    sys.exit(main())
