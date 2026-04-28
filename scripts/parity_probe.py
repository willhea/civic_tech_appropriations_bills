"""Run the parity metrics across the full local corpus.

Loads each XML/PDF pair under ``bills/``, computes the three parity
metrics (match_path_recall, body_similarity_mean, financial_recall),
and writes one line per pair to stdout (flushed) so progress is
visible while the larger bills parse. Prints summary stats at the end.

Run::

    uv run python scripts/parity_probe.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from parsers import load_bill_tree  # noqa: E402
from parsers.parity_metrics import (  # noqa: E402
    body_similarity_per_match,
    financial_recall,
    match_path_recall,
)

BILLS_DIR = Path(__file__).resolve().parents[1] / "bills"


def main() -> None:
    pairs: list[tuple[Path, Path]] = []
    for xml_path in sorted(BILLS_DIR.glob("**/*.xml")):
        pdf_path = xml_path.with_suffix(".pdf")
        if pdf_path.exists():
            pairs.append((xml_path, pdf_path))

    print(f"Pairs: {len(pairs)}", flush=True)
    print(
        f"{'Bill / Version':50s} {'XML':>5s} {'PDF':>5s} {'Recall':>7s} {'BodySim':>8s} {'Fin':>7s} {'Time':>6s}",
        flush=True,
    )
    print("-" * 105, flush=True)

    results: list[tuple[float, float, float]] = []
    skipped_empty_xml = 0
    errors: list[tuple[Path, str]] = []

    for xml_path, pdf_path in pairs:
        label = f"{xml_path.parent.name}/{xml_path.stem}"
        t0 = time.time()
        try:
            xml_t = load_bill_tree(xml_path)
            if len(xml_t.nodes) == 0:
                skipped_empty_xml += 1
                print(f"{label:50s} (empty XML — skipped)", flush=True)
                continue
            pdf_t = load_bill_tree(pdf_path)
            recall = match_path_recall(xml_t, pdf_t)
            sims = body_similarity_per_match(xml_t, pdf_t)
            body = sum(sims.values()) / len(sims) if sims else 0.0
            fin = financial_recall(xml_t, pdf_t)
            elapsed = time.time() - t0
            results.append((recall, body, fin))
            print(
                f"{label:50s} {len(xml_t.nodes):5d} {len(pdf_t.nodes):5d} "
                f"{recall:7.3f} {body:8.3f} {fin:7.3f} {elapsed:5.1f}s",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001
            errors.append((xml_path, str(e)))
            print(f"{label:50s} ERROR: {e}", flush=True)

    print("-" * 105, flush=True)
    print(f"Skipped (empty XML): {skipped_empty_xml}", flush=True)
    print(f"Errors: {len(errors)}", flush=True)
    print(flush=True)

    if not results:
        return
    n = len(results)
    avg_recall = sum(r[0] for r in results) / n
    avg_body = sum(r[1] for r in results) / n
    avg_fin = sum(r[2] for r in results) / n
    print(f"Average over {n} pairs: recall={avg_recall:.3f}, body_sim={avg_body:.3f}, fin={avg_fin:.3f}")
    print("Floors:                 recall=0.500, body_sim=0.700, fin=0.800")

    above_recall = sum(1 for r in results if r[0] >= 0.50)
    above_body = sum(1 for r in results if r[1] >= 0.70)
    above_fin = sum(1 for r in results if r[2] >= 0.80)
    print(
        f"Pairs above floor: recall {above_recall}/{n} ({above_recall * 100 / n:.0f}%), "
        f"body_sim {above_body}/{n} ({above_body * 100 / n:.0f}%), "
        f"fin {above_fin}/{n} ({above_fin * 100 / n:.0f}%)"
    )


if __name__ == "__main__":
    sys.exit(main())
