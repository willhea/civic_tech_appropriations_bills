"""Generate canonical diff JSON samples for the prototype UI demo.

Run from the repo root:

    .venv/bin/python prototype/generate_samples.py

Produces three files under prototype/sample-diffs/:
  - hr4366-reported-vs-engrossed-xml.json   (real XML pair)
  - hr4366-reported-vs-engrossed-pdf.json   (real PDF pair, same bill for cross-pipeline check)
  - synthetic-edge-cases.json               (renumbered, relocated, degraded, financial)

The synthetic file is hand-built to exercise change types the real corpus
doesn't reliably surface (PDF "renumbered" moves, degraded anchors).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Make the repo root importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bill_tree import normalize_bill  # noqa: E402
from diff_bill import bill_diff_to_dict, diff_bills, filter_diff  # noqa: E402
from diff_pdf import diff_pdfs  # noqa: E402
from formatters.canonical import (  # noqa: E402
    SCHEMA_VERSION,
    pdf_diff_to_canonical,
    xml_diff_to_canonical,
)
from parsers.pdf_text import extract_clean_pages  # noqa: E402

OUT_DIR = ROOT / "prototype" / "sample-diffs"


def _validate(canonical: dict, label: str) -> None:
    """Best-effort schema validation -- skipped silently if jsonschema isn't
    installed, since the unit tests already cover this path."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return
    schema = json.loads((OUT_DIR / "schema.json").read_text())
    jsonschema.validate(canonical, schema)
    print(f"  [schema OK] {label}")


def _write(canonical: dict, filename: str) -> None:
    path = OUT_DIR / filename
    path.write_text(json.dumps(canonical, indent=2))
    bytes_kb = path.stat().st_size / 1024
    n_changes = len(canonical["changes"])
    print(f"  wrote {filename}  ({n_changes} changes, {bytes_kb:.1f} KB)")


# ---------- Sample 1: HR4366 XML -------------------------------------------


def generate_hr4366_xml() -> None:
    print("Generating HR4366 XML diff (reported -> engrossed)...")
    bill_dir = ROOT / "bills" / "118-hr-4366"
    old_path = bill_dir / "1_reported-in-house.xml"
    new_path = bill_dir / "2_engrossed-in-house.xml"

    old_tree = normalize_bill(old_path)
    new_tree = normalize_bill(new_path)
    result = diff_bills(old_tree, new_tree)
    result = filter_diff(result, include_unchanged=False)
    diff_dict = bill_diff_to_dict(result, financial=True)
    diff_dict["old_version_number"] = 1
    diff_dict["new_version_number"] = 2

    canonical = xml_diff_to_canonical(diff_dict)
    _validate(canonical, "hr4366-xml")
    _write(canonical, "hr4366-reported-vs-engrossed-xml.json")


# ---------- Sample 2: HR4366 PDF -------------------------------------------


def generate_hr4366_pdf() -> None:
    print("Generating HR4366 PDF diff (reported -> engrossed)...")
    bill_dir = ROOT / "bills" / "118-hr-4366"
    old_pages = extract_clean_pages(bill_dir / "1_reported-in-house.pdf")
    new_pages = extract_clean_pages(bill_dir / "2_engrossed-in-house.pdf")
    pdf_diff = diff_pdfs(old_pages, new_pages)

    canonical = pdf_diff_to_canonical(
        pdf_diff,
        bill_type="hr",
        bill_number=4366,
        congress=118,
        v1_label="Reported in House",
        v2_label="Engrossed in House",
    )
    _validate(canonical, "hr4366-pdf")
    _write(canonical, "hr4366-reported-vs-engrossed-pdf.json")


# ---------- Sample 3: synthetic edge cases ---------------------------------


@dataclass
class _SynChange:
    change_type: str
    section_number: str
    path_v1: list[str] | None
    path_v2: list[str] | None
    location_v1: dict | None
    location_v2: dict | None
    text_old: str | None
    text_new: str | None
    amounts: list[dict]
    move: dict | None
    anchor_resolution: str = "resolved"


def _to_dict(c: _SynChange, idx: int) -> dict:
    return {
        "id": f"c-{idx + 1:04d}",
        "change_type": c.change_type,
        "section_number": c.section_number,
        "path": {"v1": c.path_v1, "v2": c.path_v2},
        "location": (
            None if c.location_v1 is None and c.location_v2 is None else {"v1": c.location_v1, "v2": c.location_v2}
        ),
        "anchor_resolution": c.anchor_resolution,
        "text": {"old": c.text_old, "new": c.text_new},
        "amounts": c.amounts,
        "move": c.move,
    }


def generate_synthetic() -> None:
    print("Generating synthetic edge-case diff...")
    changes = [
        _SynChange(
            change_type="modified",
            section_number="101",
            path_v1=["TITLE I", "Department of Customs", "Sec. 101"],
            path_v2=["TITLE I", "Department of Customs", "Sec. 101"],
            location_v1={"start_page": 12, "start_line": 4, "end_page": 12, "end_line": 18},
            location_v2={"start_page": 13, "start_line": 1, "end_page": 13, "end_line": 14},
            text_old=(
                "For necessary expenses of the Department of Customs, $5,000,000, to remain "
                "available until September 30, 2027."
            ),
            text_new=(
                "For necessary expenses of the Department of Customs, $5,500,000, to remain "
                "available until September 30, 2028."
            ),
            amounts=[{"old": 5000000, "new": 5500000}],
            move=None,
        ),
        _SynChange(
            change_type="added",
            section_number="",
            path_v1=None,
            path_v2=["TITLE II", "Office of Innovation"],
            location_v1=None,
            location_v2={"start_page": 24, "start_line": 1, "end_page": 25, "end_line": 30},
            text_old=None,
            text_new=(
                "There is established within the Department an Office of Innovation, headed "
                "by a Director appointed by the Secretary."
            ),
            amounts=[],
            move=None,
        ),
        _SynChange(
            change_type="removed",
            section_number="307",
            path_v1=["TITLE III", "General Provisions", "Sec. 307"],
            path_v2=None,
            location_v1={"start_page": 41, "start_line": 8, "end_page": 41, "end_line": 22},
            location_v2=None,
            text_old=(
                "None of the funds made available by this Act may be used to finalize the "
                "rule proposed in 89 Fed. Reg. 12,345."
            ),
            text_new=None,
            amounts=[],
            move=None,
        ),
        _SynChange(
            change_type="moved",
            section_number="",
            path_v1=["TITLE IV", "Sec. 401"],
            path_v2=["TITLE IV", "Sec. 501"],
            location_v1={"start_page": 52, "start_line": 1, "end_page": 53, "end_line": 4},
            location_v2={"start_page": 61, "start_line": 1, "end_page": 62, "end_line": 4},
            text_old="Reporting requirement on quarterly obligations to the Committees on Appropriations.",
            text_new="Reporting requirement on quarterly obligations to the Committees on Appropriations.",
            amounts=[],
            move={"kind": "renumbered", "old_label": "Sec. 401", "new_label": "Sec. 501", "body_unchanged": True},
        ),
        _SynChange(
            change_type="moved",
            section_number="",
            path_v1=["TITLE V", "Subtitle A", "Sec. 502"],
            path_v2=["TITLE V", "Subtitle B", "Sec. 502"],
            location_v1={"start_page": 70, "start_line": 1, "end_page": 70, "end_line": 12},
            location_v2={"start_page": 75, "start_line": 1, "end_page": 75, "end_line": 12},
            text_old="Limitation on transfer authority for the Defense Working Capital Fund.",
            text_new="Limitation on transfer authority for the Defense Working Capital Fund.",
            amounts=[],
            move={"kind": "relocated", "body_unchanged": True},
        ),
        _SynChange(
            change_type="modified",
            section_number="",
            path_v1=None,
            path_v2=None,
            location_v1={"start_page": 88, "start_line": None, "end_page": 88, "end_line": None},
            location_v2={"start_page": 91, "start_line": None, "end_page": 91, "end_line": None},
            text_old="Provided further, That amounts under this heading shall be available for fiscal year 2027.",
            text_new="Provided further, That amounts under this heading shall be available for fiscal year 2028.",
            amounts=[],
            move=None,
            anchor_resolution="degraded",
        ),
    ]

    canonical = {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": "appropriations_bills", "version": "0-synthetic"},
        "bill": {"type": "HR", "number": "DEMO-2026", "congress": 119},
        "versions": {
            "v1": {"label": "Committee Print", "version_number": 1, "source": "pdf"},
            "v2": {"label": "Floor Manager's Mark", "version_number": 2, "source": "pdf"},
        },
        "summary": {"added": 1, "removed": 1, "modified": 2, "moved": 2},
        "changes": [_to_dict(c, i) for i, c in enumerate(changes)],
    }
    _validate(canonical, "synthetic")
    _write(canonical, "synthetic-edge-cases.json")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_hr4366_xml()
    generate_hr4366_pdf()
    generate_synthetic()
    print("\nDone.")


if __name__ == "__main__":
    main()
