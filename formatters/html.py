"""XML diff -> HTML report. Thin shim over the unified renderer.

format_html(diff_dict) is the historical entry point used by render_examples.py
and diff_bill.py's --output html flag. It delegates to formatters.diff_html
via the XML adapter; the unified renderer makes canonical visual choices
shared with the PDF pipeline.

word_diff and fmt_dollar are re-exported for callers that have imported them
from this module historically.
"""

from formatters._text import fmt_dollar, word_diff
from formatters.adapters import xml_dict_to_view
from formatters.diff_html import format_diff_html

__all__ = ["format_html", "fmt_dollar", "word_diff"]


def format_html(diff_dict: dict) -> str:
    """Assemble a complete standalone HTML report from a bill diff dict."""
    return format_diff_html(xml_dict_to_view(diff_dict))
