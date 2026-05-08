"""PDF diff -> HTML report. Thin shim over the unified renderer.

format_pdf_html(diff, ...) is the historical entry point used by
render_examples.py and PDF-pipeline scripts. It delegates to
formatters.diff_html via the PDF adapter; the unified renderer makes
canonical visual choices shared with the XML pipeline.

word_diff and fmt_dollar are re-exported for callers that have imported
them from this module historically.
"""

from __future__ import annotations

from diff_pdf import PdfDiff
from formatters._text import fmt_dollar, word_diff
from formatters.adapters import pdf_diff_to_view
from formatters.diff_html import format_diff_html

__all__ = ["format_pdf_html", "fmt_dollar", "word_diff"]


def format_pdf_html(
    diff: PdfDiff,
    *,
    bill_type: str,
    bill_number: str | int,
    congress: int | str,
    v1_label: str = "v1",
    v2_label: str = "v2",
) -> str:
    """Assemble a complete standalone HTML report from a PdfDiff."""
    return format_diff_html(
        pdf_diff_to_view(
            diff,
            bill_type=bill_type,
            bill_number=bill_number,
            congress=congress,
            v1_label=v1_label,
            v2_label=v2_label,
        )
    )
