"""Neutral view model consumed by the unified diff renderer.

Both the XML pipeline (via formatters.adapters.xml_dict_to_view) and the
PDF pipeline (via formatters.adapters.pdf_diff_to_view) target this shape.
The renderer in formatters.diff_html consumes it without knowing which
pipeline produced it.

PDF-only fields default to "absent" values (None / False / "" / ()) so the
XML adapter can ignore them and the renderer can branch on presence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChangeView:
    change_type: str
    """One of: added, removed, modified, moved, unchanged."""

    heading_html: str
    """Pre-escaped HTML ready to drop directly into the card <h3>."""

    nav_label_html: str
    """Pre-escaped HTML for the sidebar nav-item label."""

    nav_extra_class: str
    """Extra CSS class on the nav-item ("" or "unanchored")."""

    group_key: str
    """Stable key used by the financial-summary table for rowspan grouping."""

    section_number: str
    """Section number prefix for the sidebar label, or "" when absent."""

    old_text: str | None
    """Raw old text. The renderer escapes."""

    new_text: str | None
    """Raw new text. The renderer escapes."""

    citation_html: str | None
    """Pre-rendered citation block. None for XML; a <div class="citation">... for PDF."""

    degraded: bool
    """When True, card and nav item gain "unanchored" / "degraded" classes."""

    amount_pairs: tuple[tuple[int | None, int | None], ...]
    """Old/new amount pairs, with None for one-sided amounts."""

    has_amendment_annotations: bool
    """When True, financial callouts include the floor-amendment-annotation note."""

    summary_amount_filter: str
    """Per-pipeline filter selector: "amounts_changed" (XML) or "real_change" (PDF)."""


@dataclass(frozen=True)
class DiffView:
    bill_type: str
    bill_number: int
    congress: int
    v1_label: str
    v2_label: str
    summary: dict[str, int]
    changes: tuple[ChangeView, ...] = field(default_factory=tuple)
