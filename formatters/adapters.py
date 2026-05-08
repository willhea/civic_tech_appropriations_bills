"""Adapters from pipeline-specific diff shapes into the neutral DiffView.

XML pipeline: dict produced by bill_diff_to_dict -> xml_dict_to_view.
PDF pipeline: PdfDiff dataclass -> pdf_diff_to_view.
"""

from __future__ import annotations

from html import escape

from diff_pdf import PdfDiff, PdfHunk
from formatters.view_model import ChangeView, DiffView
from parsers.pdf_anchors import Anchor, breadcrumb_for

# ---------- Shared helpers ----------------------------------------------------


def _real_changes(
    pairs: tuple[tuple[int | None, int | None], ...],
) -> tuple[tuple[int | None, int | None], ...]:
    """Keep only pairs where both sides are present and differ.

    Pairs where one side is None (pure annotation insertions) and pairs
    where old == new (no change) drop out, so the financial callout and
    summary table render only meaningful base-amount changes.
    """
    return tuple((old, new) for old, new in pairs if old is not None and new is not None and old != new)


# ---------- XML adapter -------------------------------------------------------


def _pair_amounts(financial: dict | None) -> tuple[tuple[int | None, int | None], ...]:
    """Resolve the (old, new) amount pairs for a single XML change.

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


def _join_path(parts: list[str] | None) -> str:
    """Join a path with the canonical ' &gt; ' separator, escaping each segment.

    Per-segment escape is required so that a literal '>' inside a segment
    doesn't masquerade as a separator after escaping.
    """
    if not parts:
        return ""
    return " &gt; ".join(escape(p) for p in parts)


def _xml_heading_html(change: dict) -> str:
    """Pre-rendered heading. Prefer the new path; fall back to old (for removed)."""
    parts = change.get("display_path_new") or change.get("display_path_old") or []
    return _join_path(parts)


def _xml_nav_label_html(change: dict) -> str:
    """Pre-rendered sidebar label. '(unknown)' when no path is available."""
    parts = change.get("display_path_new") or change.get("display_path_old") or []
    if not parts:
        return "(unknown)"
    return _join_path(parts)


def _xml_move_info_html(change: dict) -> str:
    """Pre-rendered move-info div for change_type=='moved'.

    XML diffs don't carry anchor-text identifiers, so we always use the
    path-based form: 'Moved: old_path → new_path'. The PDF adapter has
    a richer 'Renumbered' branch when anchor texts differ.
    """
    if change.get("change_type") != "moved":
        return ""
    old_path = _join_path(change.get("display_path_old"))
    new_path = _join_path(change.get("display_path_new"))
    return f'<div class="move-info">Moved: {old_path} &rarr; {new_path}</div>'


def _change_view_from_xml(change: dict) -> ChangeView:
    financial = change.get("financial")
    pairs = _pair_amounts(financial)
    return ChangeView(
        change_type=change.get("change_type", "modified"),
        heading_html=_xml_heading_html(change),
        nav_label_html=_xml_nav_label_html(change),
        section_number=change.get("section_number") or "",
        citation_html="",
        degraded=False,
        move_info_html=_xml_move_info_html(change),
        old_text=change.get("old_text") or "",
        new_text=change.get("new_text") or "",
        amount_pairs=_real_changes(pairs),
    )


def xml_dict_to_view(diff_dict: dict) -> DiffView:
    """Convert a bill-diff dict (from bill_diff_to_dict) into a DiffView.

    Drops `unchanged` entries up front: bill_diff_to_dict emits a card per
    matched node regardless of whether it changed, but the renderer should
    only show items with diffs.
    """
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
        changes=tuple(_change_view_from_xml(c) for c in changes if c.get("change_type") != "unchanged"),
    )


# ---------- PDF adapter -------------------------------------------------------


def _pdf_breadcrumb_html(anchor: Anchor | None, all_anchors: tuple[Anchor, ...]) -> str | None:
    """Pre-render the breadcrumb chain for an anchor as HTML-escaped path.

    Returns None when the anchor is missing — the caller decides the fallback.
    """
    if anchor is None:
        return None
    chain = breadcrumb_for(anchor, all_anchors)
    return " &gt; ".join(escape(part) for part in chain)


def _pdf_format_range(rng: tuple[int, int, int, int] | None) -> str:
    """Render a (start_page, start_line, end_page, end_line) tuple.

    Lines with `-1` (unnumbered source) render as `p.X` without the line.
    """
    if rng is None:
        return "—"
    sp, sl, ep, el = rng
    start = f"p.{sp}" if sl < 0 else f"p.{sp} L{sl}"
    end = f"p.{ep}" if el < 0 else f"p.{ep} L{el}"
    if start == end:
        return start
    return f"{start} – {end}"


def _pdf_citation_html(hunk: PdfHunk) -> str:
    """Render the v1/v2 page+line citation block for a card."""
    parts = ['<div class="citation">']
    if hunk.v1_range is None:
        parts.append('<span class="v1">— (new in v2)</span>')
    else:
        parts.append(f'<span class="v1">{escape(_pdf_format_range(hunk.v1_range))}</span>')
    if hunk.v2_range is None:
        parts.append('<span class="v2">— (removed in v2)</span>')
    else:
        parts.append(f'<span class="v2">{escape(_pdf_format_range(hunk.v2_range))}</span>')
    parts.append("</div>")
    return "".join(parts)


def _pdf_heading_and_nav(
    hunk: PdfHunk,
    v1_anchors: tuple[Anchor, ...],
    v2_anchors: tuple[Anchor, ...],
) -> tuple[str, str, bool]:
    """Resolve (heading_html, nav_label_html, degraded) for a PDF hunk.

    Prefer v2 breadcrumb (where the change lands) over v1 (for removed hunks).
    When neither resolves, fall back to a placeholder heading + a page+line
    nav label so the sidebar entry is still navigable.
    """
    v2_crumb = _pdf_breadcrumb_html(hunk.v2_anchor, v2_anchors)
    v1_crumb = _pdf_breadcrumb_html(hunk.v1_anchor, v1_anchors)
    crumb = v2_crumb or v1_crumb
    if crumb is not None:
        return crumb, crumb, False
    # Degraded: no anchor resolved on either side.
    rng = hunk.v2_range or hunk.v1_range
    nav_label = f"(uncategorized) — {escape(_pdf_format_range(rng))}"
    heading = "anchor unresolved · see PDF for context"
    return heading, nav_label, True


def _pdf_move_info_html(
    hunk: PdfHunk,
    v1_anchors: tuple[Anchor, ...],
    v2_anchors: tuple[Anchor, ...],
) -> str:
    """Pre-rendered move-info div for change_type=='moved'.

    When both anchors resolve and their texts differ, use the canonical
    "Renumbered: <code>X</code> → <code>Y</code>" form, with a
    "body text unchanged" suffix when v1_text == v2_text. Otherwise fall
    back to "Moved: v1_breadcrumb → v2_breadcrumb" using whatever path
    resolves (page-range fallback when the breadcrumb is missing).
    """
    if hunk.change_type != "moved":
        return ""
    if hunk.v1_anchor is not None and hunk.v2_anchor is not None and hunk.v1_anchor.text != hunk.v2_anchor.text:
        label = (
            f"Renumbered: <code>{escape(hunk.v1_anchor.text)}</code> &rarr; <code>{escape(hunk.v2_anchor.text)}</code>"
        )
        if hunk.v1_text == hunk.v2_text:
            label += " · body text unchanged"
    else:
        v1_crumb = _pdf_breadcrumb_html(hunk.v1_anchor, v1_anchors) or escape(_pdf_format_range(hunk.v1_range))
        v2_crumb = _pdf_breadcrumb_html(hunk.v2_anchor, v2_anchors) or escape(_pdf_format_range(hunk.v2_range))
        label = f"Moved: {v1_crumb} &rarr; {v2_crumb}"
    return f'<div class="move-info">{label}</div>'


def _change_view_from_pdf(
    hunk: PdfHunk,
    v1_anchors: tuple[Anchor, ...],
    v2_anchors: tuple[Anchor, ...],
) -> ChangeView:
    heading_html, nav_label_html, degraded = _pdf_heading_and_nav(hunk, v1_anchors, v2_anchors)
    return ChangeView(
        change_type=hunk.change_type,
        heading_html=heading_html,
        nav_label_html=nav_label_html,
        section_number="",
        citation_html=_pdf_citation_html(hunk),
        degraded=degraded,
        move_info_html=_pdf_move_info_html(hunk, v1_anchors, v2_anchors),
        old_text=hunk.v1_text or "",
        new_text=hunk.v2_text or "",
        amount_pairs=_real_changes(hunk.amount_pairs),
    )


def pdf_diff_to_view(
    diff: PdfDiff,
    *,
    bill_type: str,
    bill_number: int | str,
    congress: int | str,
    v1_label: str = "v1",
    v2_label: str = "v2",
) -> DiffView:
    """Convert a PdfDiff into a DiffView.

    PDFs don't carry version-index numbers, so v1_version_number and
    v2_version_number are always None — the renderer skips the "v1: " prefix
    in the versions line when both are None.
    """
    return DiffView(
        bill_type=bill_type,
        bill_number=bill_number,
        congress=congress,
        v1_label=v1_label,
        v2_label=v2_label,
        v1_version_number=None,
        v2_version_number=None,
        summary=dict(diff.summary),
        changes=tuple(_change_view_from_pdf(h, diff.v1_anchors, diff.v2_anchors) for h in diff.hunks),
    )
