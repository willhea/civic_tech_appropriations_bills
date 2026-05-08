"""Adapters from pipeline-specific diff shapes into the neutral DiffView.

XML pipeline: dict produced by bill_diff_to_dict -> xml_dict_to_view.
PDF pipeline: PdfDiff dataclass -> pdf_diff_to_view (added in the next step).
"""

from __future__ import annotations

from html import escape

from formatters.view_model import ChangeView, DiffView


def _pair_amounts(financial: dict | None) -> tuple[tuple[int | None, int | None], ...]:
    """Resolve the (old, new) amount pairs for a single change.

    Prefers `paired_amounts` (already aligned upstream); falls back to
    positional pairing of `old_amounts` and `new_amounts`. Returns the
    pairs unfiltered — the caller decides what counts as "real."
    """
    if not financial:
        return ()
    paired = financial.get("paired_amounts")
    if paired:
        return tuple((p[0], p[1]) for p in paired)
    old_amounts = financial.get("old_amounts", []) or []
    new_amounts = financial.get("new_amounts", []) or []
    n = max(len(old_amounts), len(new_amounts))
    return tuple(
        (
            old_amounts[i] if i < len(old_amounts) else None,
            new_amounts[i] if i < len(new_amounts) else None,
        )
        for i in range(n)
    )


def _real_changes(
    pairs: tuple[tuple[int | None, int | None], ...],
) -> tuple[tuple[int | None, int | None], ...]:
    """Keep only pairs where both sides are present and differ.

    This is the canonical filter (PDF-style). Pure annotation insertions
    (one-sided None) belong in the per-card callout via the
    has_amendment_annotations flag, not as financial-summary rows.
    """
    return tuple((old, new) for old, new in pairs if old is not None and new is not None and old != new)


def _join_path(parts: list[str] | None) -> str:
    """Join a path with the canonical ' &gt; ' separator, escaping each segment.

    Per-segment escape is required so that a literal '>' inside a segment
    doesn't masquerade as a separator after escaping.
    """
    if not parts:
        return ""
    return " &gt; ".join(escape(p) for p in parts)


def _heading_html(change: dict) -> str:
    """Pre-rendered heading. Prefer the new path; fall back to old (for removed)."""
    parts = change.get("display_path_new") or change.get("display_path_old") or []
    return _join_path(parts)


def _nav_label_html(change: dict) -> str:
    """Pre-rendered sidebar label. '(unknown)' when no path is available.

    The renderer separately prefixes the section number when the change has one.
    """
    parts = change.get("display_path_new") or change.get("display_path_old") or []
    if not parts:
        return "(unknown)"
    return _join_path(parts)


def _move_info_html(change: dict) -> str:
    """Pre-rendered move-info div for change_type=='moved'.

    XML diffs don't carry anchor-text identifiers, so we always use the
    path-based form: 'Moved: old_path → new_path'. (The PDF adapter has
    a richer 'Renumbered' branch when anchor texts differ.)
    """
    if change.get("change_type") != "moved":
        return ""
    old_path = _join_path(change.get("display_path_old"))
    new_path = _join_path(change.get("display_path_new"))
    return f'<div class="move-info">Moved: {old_path} &rarr; {new_path}</div>'


def _change_view_from_xml(change: dict, index: int) -> ChangeView:
    financial = change.get("financial")
    pairs = _pair_amounts(financial)
    return ChangeView(
        change_type=change.get("change_type", "modified"),
        heading_html=_heading_html(change),
        nav_label_html=_nav_label_html(change),
        section_number=change.get("section_number") or "",
        citation_html="",
        degraded=False,
        move_info_html=_move_info_html(change),
        old_text=change.get("old_text") or "",
        new_text=change.get("new_text") or "",
        amount_pairs=_real_changes(pairs),
        has_amendment_annotations=bool(financial and financial.get("has_amendment_annotations")),
        group_key=f"xml-{index}",
    )


def xml_dict_to_view(diff_dict: dict) -> DiffView:
    """Convert a bill-diff dict (from bill_diff_to_dict) into a DiffView."""
    changes = diff_dict.get("changes", []) or []
    return DiffView(
        bill_type=diff_dict.get("bill_type", "") or "",
        bill_number=diff_dict.get("bill_number", "") or "",
        congress=diff_dict.get("congress", "") or "",
        v1_label=diff_dict.get("old_version", "") or "",
        v2_label=diff_dict.get("new_version", "") or "",
        v1_version_number=diff_dict.get("old_version_number"),
        v2_version_number=diff_dict.get("new_version_number"),
        summary=dict(diff_dict.get("summary") or {}),
        changes=tuple(_change_view_from_xml(c, i) for i, c in enumerate(changes)),
    )
