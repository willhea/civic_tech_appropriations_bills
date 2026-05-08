"""Neutral view model consumed by the unified diff renderer.

Both the XML pipeline (via formatters.adapters.xml_dict_to_view) and the
PDF pipeline (via formatters.adapters.pdf_diff_to_view) target this shape.
The renderer in formatters.diff_html consumes it without knowing which
pipeline produced it.

Pipeline-specific HTML fragments (heading_html, nav_label_html,
citation_html, move_info_html) are pre-rendered by the adapters so the
renderer doesn't need to know about XML display paths or PDF anchor
breadcrumbs. Optional/PDF-only fields default to empty/False so that the
renderer's branches are driven by data presence, not by pipeline identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ChangeType = Literal["added", "removed", "modified", "moved"]


@dataclass(frozen=True)
class ChangeView:
    change_type: ChangeType
    """The diff classifier. Constrained to a known set so the renderer can
    rely on it for class names without runtime sanitization."""

    heading_html: str
    """Pre-escaped HTML ready to drop directly into the card <h3>."""

    nav_label_html: str
    """Pre-escaped HTML for the sidebar nav-item label (excluding section prefix)."""

    section_number: str
    """Section number string. Empty when absent. The renderer emits a separate
    <span class="section-number"> when set, and prefixes the sidebar label."""

    citation_html: str
    """Pre-rendered citation block. "" for XML; full <div class="citation">
    ... </div> for PDF."""

    degraded: bool
    """When True, card and nav item gain "unanchored" / "degraded" classes."""

    move_info_html: str
    """Pre-rendered move-info div for change_type=="moved". "" otherwise."""

    old_text: str
    """Old text body. "" when absent."""

    new_text: str
    """New text body. "" when absent."""

    amount_pairs: tuple[tuple[int | None, int | None], ...]
    """Already filtered to "real" amount changes (both sides present and
    differing). The renderer iterates without re-filtering."""


@dataclass(frozen=True)
class DiffView:
    bill_type: str
    bill_number: int | str
    congress: int | str
    v1_label: str
    v2_label: str
    v1_version_number: int | None
    """Version index (1, 2, ...) when known. Drives the "v1: " prefix in the
    rendered versions line. None for PDFs (no version index available)."""
    v2_version_number: int | None
    summary: dict[str, int]
    changes: tuple[ChangeView, ...] = field(default_factory=tuple)
