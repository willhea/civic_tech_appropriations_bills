"""Bill-format parsers that all produce a normalized :class:`BillTree`.

``load_bill_tree(path)`` dispatches by file extension. Currently
supported: ``.xml`` and ``.pdf``. ``.docx`` is reserved for a future
iteration and raises with an explanatory message so a stale CLI call
fails fast.
"""

from __future__ import annotations

from pathlib import Path

from bill_tree import BillTree

from .pdf_parser import parse_pdf
from .xml_parser import parse_xml

SUPPORTED_EXTENSIONS = (".xml", ".pdf")


class UnsupportedFormatError(ValueError):
    """Raised when ``load_bill_tree`` receives an unsupported extension."""


def load_bill_tree(path: Path) -> BillTree:
    """Parse a bill file into a :class:`BillTree`, dispatching by extension."""
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return parse_xml(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".docx":
        raise UnsupportedFormatError(
            "Word (.docx) input is not supported in the current scope; supported formats: .xml, .pdf"
        )
    raise UnsupportedFormatError(
        f"Unsupported bill format {suffix!r}; supported formats: " + ", ".join(SUPPORTED_EXTENSIONS)
    )


__all__ = ["BillTree", "UnsupportedFormatError", "load_bill_tree", "SUPPORTED_EXTENSIONS"]
