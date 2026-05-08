"""Canonical diff JSON producers and the consumer that rebuilds DiffView.

The canonical JSON is the public contract for diff results — pipeline-neutral,
versioned, semantic-only (no pre-rendered HTML). See
prototype/sample-diffs/schema.md for the prose spec and schema.json for the
JSON Schema.

Two producers, one consumer:

  xml_diff_to_canonical(diff_dict)        -> dict   # from bill_diff_to_dict output
  pdf_diff_to_canonical(pdf_diff, **meta) -> dict   # from PdfDiff

  view_from_canonical(canonical) -> DiffView        # rebuilds renderer-facing view

view_from_canonical lets the existing HTML renderer (formatters.diff_html)
consume canonical JSON without code changes, and gives the round-trip
parity tests something to assert against.
"""

from __future__ import annotations

from html import escape

from diff_pdf import PdfDiff, PdfHunk
from formatters.view_model import ChangeView, DiffView
from parsers.pdf_anchors import Anchor, breadcrumb_for

SCHEMA_VERSION = "1.1"
GENERATOR_NAME = "appropriations_bills"


# ---------- Shared helpers ---------------------------------------------------


def _real_amount_pairs(
    pairs: tuple[tuple[int | None, int | None], ...] | list,
) -> list[dict]:
    """Filter pairs to "real" changes and emit canonical dict form.

    Mirrors formatters.adapters._real_changes: keep pairs where both sides
    are present and old != new. The producer guarantees this filter so a
    consumer reading the JSON doesn't have to reimplement it.
    """
    return [{"old": old, "new": new} for old, new in pairs if old is not None and new is not None and old != new]


def _make_id(index: int) -> str:
    return f"c-{index + 1:04d}"


# ---------- XML producer -----------------------------------------------------


def _xml_change_to_canonical(change: dict, index: int) -> dict:
    change_type = change.get("change_type", "modified")
    path_old = change.get("display_path_old")
    path_new = change.get("display_path_new")
    return {
        "id": _make_id(index),
        "change_type": change_type,
        "section_number": change.get("section_number") or "",
        "path": {
            "v1": list(path_old) if path_old else None,
            "v2": list(path_new) if path_new else None,
        },
        "location": None,  # XML carries no source coordinates
        "anchor_resolution": "resolved",  # XML pipeline always resolves structurally
        "text": {
            "old": change.get("old_text"),
            "new": change.get("new_text"),
        },
        "amounts": _real_amount_pairs((change.get("financial") or {}).get("paired_amounts", ())),
        "move": _xml_move(change) if change_type == "moved" else None,
    }


def _xml_move(change: dict) -> dict:
    """XML pipeline always uses path-form moves -- there's no anchor-text identifier
    that could be 'renumbered'."""
    return {
        "kind": "relocated",
        "body_unchanged": (change.get("old_text") or "") == (change.get("new_text") or ""),
    }


def xml_diff_to_canonical(diff_dict: dict, *, full_text: dict | None = None) -> dict:
    """Convert a bill-diff dict (from bill_diff_to_dict) into canonical JSON.

    Drops `unchanged` entries: bill_diff_to_dict emits a card per matched node,
    but the canonical JSON only carries actual diffs.

    `full_text`, when provided, must be a dict with string keys "v1" and "v2"
    holding the complete serialized bill text per side. The canonical JSON
    surfaces it at the top level for full-document rendering.
    """
    diffed = [c for c in (diff_dict.get("changes") or []) if c.get("change_type") != "unchanged"]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": "0"},
        "bill": {
            "type": diff_dict.get("bill_type", "") or "",
            "number": diff_dict.get("bill_number", "") or "",
            "congress": diff_dict.get("congress", "") or "",
        },
        "versions": {
            "v1": {
                "label": diff_dict.get("old_version", "") or "",
                "version_number": diff_dict.get("old_version_number"),
                "source": "xml",
            },
            "v2": {
                "label": diff_dict.get("new_version", "") or "",
                "version_number": diff_dict.get("new_version_number"),
                "source": "xml",
            },
        },
        "summary": dict(diff_dict.get("summary") or {}),
        "full_text": _normalize_full_text(full_text),
        "changes": [_xml_change_to_canonical(c, i) for i, c in enumerate(diffed)],
    }


def _normalize_full_text(full_text: dict | None) -> dict | None:
    """Validate and pass through the optional full_text field.

    Accepts None for "no full text available," or a dict with string v1/v2
    keys. Anything else raises -- the producer is the gatekeeper for the
    schema, not the consumer.
    """
    if full_text is None:
        return None
    if not isinstance(full_text, dict) or set(full_text) != {"v1", "v2"}:
        raise ValueError("full_text must be None or a dict with keys 'v1' and 'v2'")
    if not all(isinstance(full_text[k], str) for k in ("v1", "v2")):
        raise ValueError("full_text values must be strings")
    return {"v1": full_text["v1"], "v2": full_text["v2"]}


# ---------- PDF producer -----------------------------------------------------


def _line_or_none(line: int) -> int | None:
    """PdfHunk encodes unnumbered source lines as -1; canonical uses null."""
    return None if line < 0 else line


def _range_to_canonical(rng: tuple[int, int, int, int] | None) -> dict | None:
    if rng is None:
        return None
    sp, sl, ep, el = rng
    return {
        "start_page": sp,
        "start_line": _line_or_none(sl),
        "end_page": ep,
        "end_line": _line_or_none(el),
    }


def _path_for_anchor(anchor: Anchor | None, all_anchors: tuple[Anchor, ...]) -> list[str] | None:
    if anchor is None:
        return None
    return list(breadcrumb_for(anchor, all_anchors))


def _pdf_move(hunk: PdfHunk) -> dict:
    """When both anchors resolve and their texts differ, canonical kind is
    'renumbered' (the section identifier itself changed). Otherwise it's
    'relocated' -- a move within the hierarchy without an identifier change."""
    body_unchanged = hunk.v1_text == hunk.v2_text
    if hunk.v1_anchor is not None and hunk.v2_anchor is not None and hunk.v1_anchor.text != hunk.v2_anchor.text:
        return {
            "kind": "renumbered",
            "old_label": hunk.v1_anchor.text,
            "new_label": hunk.v2_anchor.text,
            "body_unchanged": body_unchanged,
        }
    return {"kind": "relocated", "body_unchanged": body_unchanged}


def _pdf_hunk_to_canonical(
    hunk: PdfHunk,
    index: int,
    v1_anchors: tuple[Anchor, ...],
    v2_anchors: tuple[Anchor, ...],
) -> dict:
    path_v1 = _path_for_anchor(hunk.v1_anchor, v1_anchors)
    path_v2 = _path_for_anchor(hunk.v2_anchor, v2_anchors)
    # Degraded: neither side resolved an anchor (regardless of which sides are
    # active for this change_type). For added/removed, the absent side has no
    # anchor by definition, so we only flag degraded when the *expected* side
    # also failed to resolve.
    expected_v1 = hunk.v1_range is not None
    expected_v2 = hunk.v2_range is not None
    resolved = (path_v1 is not None) or (path_v2 is not None) or not (expected_v1 or expected_v2)
    return {
        "id": _make_id(index),
        "change_type": hunk.change_type,
        "section_number": "",  # PDF surfaces the section inside the breadcrumb instead
        "path": {"v1": path_v1, "v2": path_v2},
        "location": {
            "v1": _range_to_canonical(hunk.v1_range),
            "v2": _range_to_canonical(hunk.v2_range),
        },
        "anchor_resolution": "resolved" if resolved else "degraded",
        "text": {
            "old": hunk.v1_text if hunk.v1_range is not None else None,
            "new": hunk.v2_text if hunk.v2_range is not None else None,
        },
        "amounts": _real_amount_pairs(hunk.amount_pairs),
        "move": _pdf_move(hunk) if hunk.change_type == "moved" else None,
    }


def pdf_diff_to_canonical(
    diff: PdfDiff,
    *,
    bill_type: str,
    bill_number: int | str,
    congress: int | str,
    v1_label: str = "v1",
    v2_label: str = "v2",
    full_text: dict | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": "0"},
        "bill": {"type": bill_type, "number": bill_number, "congress": congress},
        "versions": {
            "v1": {"label": v1_label, "version_number": None, "source": "pdf"},
            "v2": {"label": v2_label, "version_number": None, "source": "pdf"},
        },
        "summary": dict(diff.summary),
        "full_text": _normalize_full_text(full_text),
        "changes": [_pdf_hunk_to_canonical(h, i, diff.v1_anchors, diff.v2_anchors) for i, h in enumerate(diff.hunks)],
    }


# ---------- Consumer: rebuild DiffView for the existing HTML renderer --------


def _join_path(parts: list[str] | None) -> str:
    if not parts:
        return ""
    return " &gt; ".join(escape(p) for p in parts)


def _format_range_str(rng: dict | None) -> str:
    """Renders 'p.X L.Y' or 'p.X' when line is null. Mirrors
    formatters.adapters._pdf_format_range so degraded labels come out byte-equal."""
    if rng is None:
        return "—"
    sp, sl, ep, el = rng["start_page"], rng["start_line"], rng["end_page"], rng["end_line"]
    start = f"p.{sp}" if sl is None else f"p.{sp} L{sl}"
    end = f"p.{ep}" if el is None else f"p.{ep} L{el}"
    if start == end:
        return start
    return f"{start} – {end}"


def _heading_and_nav(canonical_change: dict, source: str) -> tuple[str, str, bool]:
    """Returns (heading_html, nav_label_html, degraded)."""
    path_v1 = canonical_change["path"]["v1"]
    path_v2 = canonical_change["path"]["v2"]
    parts = path_v2 or path_v1 or []
    degraded = canonical_change["anchor_resolution"] == "degraded"
    if source == "xml":
        heading = _join_path(parts)
        nav = _join_path(parts) if parts else "(unknown)"
        return heading, nav, False
    # PDF
    if degraded:
        loc = canonical_change.get("location") or {}
        rng = loc.get("v2") or loc.get("v1")
        nav_label = f"(uncategorized) — {escape(_format_range_str(rng))}"
        return "anchor unresolved · see PDF for context", nav_label, True
    crumb = _join_path(parts)
    return crumb, crumb, False


def _citation_html(canonical_change: dict) -> str:
    loc = canonical_change.get("location")
    if loc is None:
        return ""
    parts = ['<div class="citation">']
    if loc["v1"] is None:
        parts.append('<span class="v1">— (new in v2)</span>')
    else:
        parts.append(f'<span class="v1">{escape(_format_range_str(loc["v1"]))}</span>')
    if loc["v2"] is None:
        parts.append('<span class="v2">— (removed in v2)</span>')
    else:
        parts.append(f'<span class="v2">{escape(_format_range_str(loc["v2"]))}</span>')
    parts.append("</div>")
    return "".join(parts)


def _move_info_html(canonical_change: dict) -> str:
    move = canonical_change.get("move")
    if move is None:
        return ""
    if move["kind"] == "renumbered":
        label = f"Renumbered: <code>{escape(move['old_label'])}</code> &rarr; <code>{escape(move['new_label'])}</code>"
        if move.get("body_unchanged"):
            label += " · body text unchanged"
        return f'<div class="move-info">{label}</div>'
    # Relocated: use breadcrumbs, falling back to page-range when path is null.
    path_v1 = canonical_change["path"]["v1"]
    path_v2 = canonical_change["path"]["v2"]
    loc = canonical_change.get("location") or {}
    v1_label = _join_path(path_v1) if path_v1 else escape(_format_range_str(loc.get("v1")))
    v2_label = _join_path(path_v2) if path_v2 else escape(_format_range_str(loc.get("v2")))
    return f'<div class="move-info">Moved: {v1_label} &rarr; {v2_label}</div>'


def _change_view_from_canonical(canonical_change: dict, source: str) -> ChangeView:
    heading_html, nav_label_html, degraded = _heading_and_nav(canonical_change, source)
    return ChangeView(
        change_type=canonical_change["change_type"],
        heading_html=heading_html,
        nav_label_html=nav_label_html,
        section_number=canonical_change.get("section_number") or "",
        citation_html=_citation_html(canonical_change),
        degraded=degraded,
        move_info_html=_move_info_html(canonical_change),
        old_text=canonical_change["text"].get("old") or "",
        new_text=canonical_change["text"].get("new") or "",
        amount_pairs=tuple((p["old"], p["new"]) for p in canonical_change.get("amounts") or ()),
    )


def view_from_canonical(canonical: dict) -> DiffView:
    source = canonical["versions"]["v1"]["source"]
    return DiffView(
        bill_type=canonical["bill"]["type"],
        bill_number=canonical["bill"]["number"],
        congress=canonical["bill"]["congress"],
        v1_label=canonical["versions"]["v1"]["label"],
        v2_label=canonical["versions"]["v2"]["label"],
        v1_version_number=canonical["versions"]["v1"]["version_number"],
        v2_version_number=canonical["versions"]["v2"]["version_number"],
        summary=dict(canonical.get("summary") or {}),
        changes=tuple(_change_view_from_canonical(c, source) for c in canonical.get("changes") or ()),
    )
