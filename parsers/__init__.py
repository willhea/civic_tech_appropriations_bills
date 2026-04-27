"""Bill-format parsers that all produce a normalized :class:`BillTree`.

``load_bill_tree(path)`` dispatches by file extension. Currently only
``.xml`` is implemented; ``.pdf`` support is being rebuilt and will
register itself here once a working extractor lands.
"""

from __future__ import annotations

from pathlib import Path

from bill_tree import BillTree

from .xml_parser import parse_xml

SUPPORTED_EXTENSIONS = (".xml",)


class UnsupportedFormatError(ValueError):
    """Raised when ``load_bill_tree`` receives an unsupported extension."""


def load_bill_tree(path: Path) -> BillTree:
    """Parse a bill file into a :class:`BillTree`, dispatching by extension."""
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return parse_xml(path)
    raise UnsupportedFormatError(
        f"Unsupported bill format {suffix!r}; supported formats: " + ", ".join(SUPPORTED_EXTENSIONS)
    )


__all__ = ["BillTree", "UnsupportedFormatError", "load_bill_tree", "SUPPORTED_EXTENSIONS"]
