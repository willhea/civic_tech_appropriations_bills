"""Regenerate the committed example HTML diffs under `examples/`.

Run from anywhere:

    uv run python render_examples.py

Each example is a rendered diff between two versions of one bill in the
corpus, checked into the repo so reviewers can see real output without
running the pipeline themselves. Re-run after any change that affects
diff output (parser, diff classifier, renderer). The output HTML is also
marked `linguist-generated=true` in `.gitattributes` so it doesn't pollute
git blame or PR diff views by default.

Add a new bill by appending to `EXAMPLES_TO_RENDER`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bill_tree import normalize_bill
from diff_bill import bill_diff_to_dict, diff_bills
from diff_pdf import diff_pdfs
from formatters.adapters import pdf_diff_to_view, xml_dict_to_view
from formatters.diff_html import format_diff_html
from parsers.pdf_text import extract_clean_pages

PROJECT_ROOT = Path(__file__).parent
BILLS = PROJECT_ROOT / "bills"
EXAMPLES = PROJECT_ROOT / "examples"


@dataclass(frozen=True)
class ExampleSpec:
    """One bill version-pair to render. Filenames follow `<n>_<label>.{xml,pdf}`."""

    bill_dir: str  # under bills/, e.g. "118-hr-8752"
    bill_type: str  # "hr", "s", etc.
    bill_number: int
    congress: int
    v1_filename_stem: str  # e.g. "1_reported-in-house"
    v2_filename_stem: str  # e.g. "2_engrossed-in-house"


EXAMPLES_TO_RENDER: list[ExampleSpec] = [
    ExampleSpec(
        bill_dir="118-hr-8752",
        bill_type="hr",
        bill_number=8752,
        congress=118,
        v1_filename_stem="1_reported-in-house",
        v2_filename_stem="2_engrossed-in-house",
    ),
]


def _version_number_from_stem(stem: str) -> int | None:
    """Extract the leading version number from a filename stem, mirroring diff_bill.cmd_compare."""
    prefix = stem.split("_", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def _label_from_stem(stem: str) -> str:
    """Extract the human-readable label after the version-number prefix."""
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 else stem


def render_xml_diff(spec: ExampleSpec) -> Path:
    bill_dir = BILLS / spec.bill_dir
    v1 = normalize_bill(bill_dir / f"{spec.v1_filename_stem}.xml")
    v2 = normalize_bill(bill_dir / f"{spec.v2_filename_stem}.xml")
    diff = diff_bills(v1, v2)
    diff_dict = bill_diff_to_dict(diff, financial=True)
    v1_num = _version_number_from_stem(spec.v1_filename_stem)
    v2_num = _version_number_from_stem(spec.v2_filename_stem)
    if v1_num is not None:
        diff_dict["old_version_number"] = v1_num
    if v2_num is not None:
        diff_dict["new_version_number"] = v2_num
    html = format_diff_html(xml_dict_to_view(diff_dict))
    out = EXAMPLES / f"{spec.bill_type}{spec.bill_number}_xml_diff.html"
    out.write_text(html)
    return out


def render_pdf_diff(spec: ExampleSpec) -> Path:
    bill_dir = BILLS / spec.bill_dir
    v1 = extract_clean_pages(bill_dir / f"{spec.v1_filename_stem}.pdf")
    v2 = extract_clean_pages(bill_dir / f"{spec.v2_filename_stem}.pdf")
    diff = diff_pdfs(v1, v2)
    html = format_diff_html(
        pdf_diff_to_view(
            diff,
            bill_type=spec.bill_type,
            bill_number=spec.bill_number,
            congress=spec.congress,
            v1_label=_label_from_stem(spec.v1_filename_stem),
            v2_label=_label_from_stem(spec.v2_filename_stem),
        )
    )
    out = EXAMPLES / f"{spec.bill_type}{spec.bill_number}_pdf_diff.html"
    out.write_text(html)
    return out


def main() -> None:
    for spec in EXAMPLES_TO_RENDER:
        for renderer in (render_xml_diff, render_pdf_diff):
            out = renderer(spec)
            print(f"Wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
