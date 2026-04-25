"""Thin XML adapter for the parsers dispatcher.

Just forwards to :func:`bill_tree.normalize_bill` so the public
``parsers.load_bill_tree`` entry point can dispatch by extension.
"""

from __future__ import annotations

from pathlib import Path

from bill_tree import BillTree, normalize_bill


def parse_xml(xml_path: Path) -> BillTree:
    return normalize_bill(xml_path)
