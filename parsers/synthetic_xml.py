"""Helpers to build a Congress.gov-shaped ElementTree from arbitrary input.

The walkers in ``bill_tree.py`` are written against the Congress.gov XML
shape: ``legis-body > division > title > {section, appropriations-*}`` (or
shallower variants). Non-XML parsers (PDF, future Word) reconstruct that
shape with these helpers and hand the root to ``normalize_bill_from_root``.

Every builder returns the newly-created element so the caller can attach
further children. Element ``id`` attributes are minted deterministically so
HTML report anchors are stable across re-parses of the same source.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterable


def synth_id(
    *,
    congress: int,
    bill_type: str,
    bill_number: int,
    tag: str,
    match_path_parts: Iterable[str],
    ordinal: int,
) -> str:
    """Mint a stable synthetic element_id for non-XML sources.

    Uses SHA1 of the bill identity + tag + match-path + ordinal so that
    re-parsing the same PDF yields the same anchors. Diff matching uses
    ``match_path``, not ``element_id``, so collisions or drift here only
    affect anchor stability — never matching correctness.
    """
    joined = "/".join(match_path_parts)
    raw = f"{congress}-{bill_type}-{bill_number}-{tag}-{joined}-{ordinal}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"syn-{digest}"


def make_root() -> tuple[ET.Element, ET.Element]:
    """Build a ``<bill><legis-body/></bill>`` skeleton.

    Returns ``(bill, legis_body)``; non-XML parsers attach divisions,
    titles, or sections to ``legis_body`` and pass ``bill`` to
    ``normalize_bill_from_root``.
    """
    bill = ET.Element("bill")
    legis_body = ET.SubElement(bill, "legis-body")
    return bill, legis_body


def _attach_enum_header(
    parent: ET.Element,
    *,
    enum: str | None,
    header: str | None,
) -> None:
    if enum is not None:
        enum_el = ET.SubElement(parent, "enum")
        enum_el.text = enum
    if header is not None:
        header_el = ET.SubElement(parent, "header")
        header_el.text = header


def make_division(
    legis_body: ET.Element,
    *,
    enum: str,
    header: str,
    element_id: str,
) -> ET.Element:
    """Append a ``<division>`` to ``legis_body`` and return it."""
    div = ET.SubElement(legis_body, "division", attrib={"id": element_id})
    _attach_enum_header(div, enum=enum, header=header)
    return div


def make_title(
    parent: ET.Element,
    *,
    header: str,
    element_id: str,
    enum: str | None = None,
) -> ET.Element:
    """Append a ``<title>`` to ``parent`` (legis-body or division) and return it."""
    title = ET.SubElement(parent, "title", attrib={"id": element_id})
    _attach_enum_header(title, enum=enum, header=header)
    return title


def _make_content_node(
    parent: ET.Element,
    *,
    tag: str,
    enum: str | None,
    header: str | None,
    body_text: str,
    element_id: str,
) -> ET.Element:
    el = ET.SubElement(parent, tag, attrib={"id": element_id})
    _attach_enum_header(el, enum=enum, header=header)
    if body_text:
        text_el = ET.SubElement(el, "text")
        text_el.text = body_text
    return el


def make_section(
    parent: ET.Element,
    *,
    enum: str | None,
    header: str,
    body_text: str,
    element_id: str,
) -> ET.Element:
    """Append a ``<section>`` to ``parent`` and return it."""
    return _make_content_node(
        parent,
        tag="section",
        enum=enum,
        header=header,
        body_text=body_text,
        element_id=element_id,
    )


def make_appro_major(
    parent: ET.Element,
    *,
    header: str,
    body_text: str,
    element_id: str,
    enum: str | None = None,
) -> ET.Element:
    return _make_content_node(
        parent,
        tag="appropriations-major",
        enum=enum,
        header=header,
        body_text=body_text,
        element_id=element_id,
    )


def make_appro_intermediate(
    parent: ET.Element,
    *,
    header: str,
    body_text: str,
    element_id: str,
    enum: str | None = None,
) -> ET.Element:
    return _make_content_node(
        parent,
        tag="appropriations-intermediate",
        enum=enum,
        header=header,
        body_text=body_text,
        element_id=element_id,
    )


def make_appro_small(
    parent: ET.Element,
    *,
    header: str,
    body_text: str,
    element_id: str,
    enum: str | None = None,
) -> ET.Element:
    return _make_content_node(
        parent,
        tag="appropriations-small",
        enum=enum,
        header=header,
        body_text=body_text,
        element_id=element_id,
    )
