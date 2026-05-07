"""Render a PdfDiff to standalone HTML, matching the approved Step 0 mock.

Mirrors the XML pipeline's layout (`formatters.html`) for staffer parity:
sidebar with filter, summary bar, optional Financial Summary table,
change cards. PDF-specific additions:
- Page/line citation block per card (`v1: p.X L… – p.Y L…`)
- Degraded-anchor card style for hunks where no preceding anchor resolves

Reuses `word_diff` from `formatters.html` for inline prose diffs.
"""

from __future__ import annotations

from html import escape

from diff_pdf import PdfDiff, PdfHunk
from formatters.html import fmt_dollar, word_diff
from parsers.pdf_anchors import Anchor, breadcrumb_for


def _format_breadcrumb(anchor: Anchor | None, all_anchors: tuple[Anchor, ...]) -> str | None:
    """Return the HTML-safe breadcrumb string, or None if the anchor is missing."""
    if anchor is None:
        return None
    chain = breadcrumb_for(anchor, all_anchors)
    return " &gt; ".join(escape(part) for part in chain)


def _format_range(rng: tuple[int, int, int, int] | None) -> str:
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


def _format_citation(hunk: PdfHunk) -> str:
    """Render the v1/v2 page+line citation block for a card."""
    parts = ['<div class="citation">']
    if hunk.v1_range is None:
        parts.append('<span class="v1">— (new in v2)</span>')
    else:
        parts.append(f'<span class="v1">{escape(_format_range(hunk.v1_range))}</span>')
    if hunk.v2_range is None:
        parts.append('<span class="v2">— (removed in v2)</span>')
    else:
        parts.append(f'<span class="v2">{escape(_format_range(hunk.v2_range))}</span>')
    parts.append("</div>")
    return "".join(parts)


def _has_real_amount_change(pairs: tuple[tuple[int | None, int | None], ...]) -> bool:
    """A 'real' base-amount change has both old and new values, and they differ.

    Pure annotation insertions (where old=None or new=None) don't qualify;
    those are floor amendment annotations on top of an unchanged base amount.
    """
    return any(old is not None and new is not None and old != new for old, new in pairs)


def _format_amount_callout(
    pairs: tuple[tuple[int | None, int | None], ...],
    has_amendment_annotations: bool = False,
) -> str:
    """Render the financial callout box for a hunk.

    Mirrors `formatters.html._financial_callout`: shows real base-amount
    changes (old→new) and a boolean note when floor amendment annotations
    are present. Does NOT enumerate individual amendments.
    """
    real_changes = [(old, new) for old, new in pairs if old is not None and new is not None]
    if not real_changes and not has_amendment_annotations:
        return ""
    parts = ['<div class="financial-callout">']
    for old, new in real_changes:
        diff = new - old
        sign = "+" if diff > 0 else ""
        delta_class = "increase" if diff > 0 else "decrease" if diff < 0 else "unchanged"
        parts.append(
            f'<div class="row"><span class="label">Amount:</span>'
            f"<span>{escape(fmt_dollar(old))} &rarr; {escape(fmt_dollar(new))}</span>"
            f'<span class="delta {delta_class}">({sign}{fmt_dollar(diff)})</span></div>'
        )
    if has_amendment_annotations:
        parts.append('<div class="amendment-note">Includes floor amendment annotations (increased/reduced by)</div>')
    parts.append("</div>")
    return "".join(parts)


def _build_card(hunk: PdfHunk, index: int, v1_anchors: tuple[Anchor, ...], v2_anchors: tuple[Anchor, ...]) -> str:
    """Render one PdfHunk as an HTML change-card."""
    v1_crumb = _format_breadcrumb(hunk.v1_anchor, v1_anchors)
    v2_crumb = _format_breadcrumb(hunk.v2_anchor, v2_anchors)
    # Prefer the v2 crumb (where the change lands in the new version) for the
    # heading; fall back to v1 (for removed hunks); else degraded.
    heading = v2_crumb or v1_crumb
    degraded = heading is None
    if degraded:
        heading = "anchor unresolved · see PDF for context"

    classes = ["change-card", hunk.change_type]
    if degraded:
        classes.append("unanchored")
    parts = [f'<div class="{" ".join(classes)}" id="change-{index}">']

    # Header
    parts.append('<div class="change-header">')
    parts.append(f'<span class="badge badge-{hunk.change_type}">{hunk.change_type}</span>')
    h3_class = ' class="degraded"' if degraded else ""
    parts.append(f"<h3{h3_class}>{heading}</h3>")
    parts.append("</div>")

    # Citation
    parts.append(_format_citation(hunk))

    # Body
    if hunk.change_type == "moved":
        v1_text = v1_crumb or "(unresolved)"
        v2_text = v2_crumb or "(unresolved)"
        if hunk.v1_anchor and hunk.v2_anchor and hunk.v1_anchor.text != hunk.v2_anchor.text:
            move_label = (
                f"Renumbered: <code>{escape(hunk.v1_anchor.text)}</code> &rarr; "
                f"<code>{escape(hunk.v2_anchor.text)}</code>"
            )
            if hunk.v1_text == hunk.v2_text:
                move_label += " · body text unchanged"
        else:
            move_label = f"Moved: {v1_text} &rarr; {v2_text}"
        parts.append(f'<div class="move-info">{move_label}</div>')
        body_text = hunk.v2_text or hunk.v1_text
        if hunk.v1_text and hunk.v2_text and hunk.v1_text != hunk.v2_text:
            inline = word_diff(hunk.v1_text, hunk.v2_text)
            if inline:
                parts.append(f'<div class="change-body diff-inline">{inline}</div>')
            else:
                parts.append(f'<div class="change-body">{escape(body_text)}</div>')
        else:
            parts.append(f'<div class="change-body">{escape(body_text)}</div>')
    elif hunk.change_type == "added":
        parts.append(f'<div class="change-body added-text">{escape(hunk.v2_text)}</div>')
    elif hunk.change_type == "removed":
        parts.append(f'<div class="change-body removed-text">{escape(hunk.v1_text)}</div>')
    else:  # modified
        inline = word_diff(hunk.v1_text, hunk.v2_text) if hunk.v1_text and hunk.v2_text else None
        if inline:
            parts.append(f'<div class="change-body diff-inline">{inline}</div>')
        else:
            parts.append('<div class="change-body">')
            parts.append(f'<div class="old-text">{escape(hunk.v1_text)}</div>')
            parts.append(f'<div class="new-text">{escape(hunk.v2_text)}</div>')
            parts.append("</div>")

    parts.append(_format_amount_callout(hunk.amount_pairs, hunk.has_amendment_annotations))
    parts.append("</div>")
    return "\n".join(parts)


def _build_sidebar(diff: PdfDiff) -> str:
    """Render the left-hand nav. Mirrors XML pipeline's sidebar styling."""
    items = []
    for i, hunk in enumerate(diff.hunks):
        v2_crumb = _format_breadcrumb(hunk.v2_anchor, diff.v2_anchors)
        v1_crumb = _format_breadcrumb(hunk.v1_anchor, diff.v1_anchors)
        label = v2_crumb or v1_crumb
        unanchored = label is None
        if unanchored:
            rng = hunk.v2_range or hunk.v1_range
            label = f"(uncategorized) — {escape(_format_range(rng))}"
        nav_class = "nav-item unanchored" if unanchored else "nav-item"
        items.append(
            f'<li class="{nav_class}" data-type="{hunk.change_type}">'
            f'<a href="#change-{i}">'
            f'<span class="badge badge-{hunk.change_type}">{hunk.change_type}</span> '
            f"{label}"
            f"</a></li>"
        )
    return (
        '<nav class="sidebar">\n'
        '<input type="text" id="sidebar-filter" placeholder="Filter sections...">\n'
        f"<ul>{''.join(items)}</ul>\n"
        "</nav>"
    )


def _build_financial_summary(diff: PdfDiff) -> str:
    """Top-of-page Financial Summary table.

    Per Will's design choice (parity with XML pipeline): only show rows where
    the base appropriation amount actually changed across versions. Hunks whose
    only numeric change is floor amendment annotations on an unchanged base
    don't appear here — they surface inside the change card's callout.

    Returns "" when there are no real base-amount changes (the renderer then
    omits the section entirely).
    """
    rows = []
    for i, hunk in enumerate(diff.hunks):
        if not _has_real_amount_change(hunk.amount_pairs):
            continue
        v2_crumb = _format_breadcrumb(hunk.v2_anchor, diff.v2_anchors)
        v1_crumb = _format_breadcrumb(hunk.v1_anchor, diff.v1_anchors)
        label = v2_crumb or v1_crumb or escape(_format_range(hunk.v2_range or hunk.v1_range))
        for old, new in hunk.amount_pairs:
            if old is None or new is None or old == new:
                continue
            diff_dollar = new - old
            sign = "+" if diff_dollar > 0 else ""
            css = "increase" if diff_dollar > 0 else "decrease" if diff_dollar < 0 else "unchanged"
            pct = f"{sign}{diff_dollar / old * 100:.1f}%" if old != 0 else "—"
            rows.append(
                f'<tr class="{css}">'
                f'<td><a href="#change-{i}">{label}</a></td>'
                f'<td class="amount">{fmt_dollar(old)}</td>'
                f'<td class="amount">{fmt_dollar(new)}</td>'
                f'<td class="amount change-amount">{sign}{fmt_dollar(diff_dollar)}</td>'
                f'<td class="amount change-amount">{pct}</td>'
                f"</tr>"
            )
    if not rows:
        return ""
    return (
        "<h2>Financial Summary</h2>\n"
        '<table class="financial-table">\n'
        "<thead><tr>"
        "<th>Section</th><th>v1 Amount</th><th>v2 Amount</th>"
        "<th>Change ($)</th><th>Change (%)</th>"
        "</tr></thead>\n"
        f"<tbody>{''.join(rows)}</tbody>\n"
        "</table>"
    )


_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, 'Times New Roman', serif; color: #222; line-height: 1.6; }
.layout { display: flex; min-height: 100vh; }

.sidebar { width: 300px; position: fixed; top: 0; left: 0; height: 100vh;
  overflow-y: auto; background: #f7f7f7; border-right: 1px solid #ddd; padding: 12px; }
.sidebar input { width: 100%; padding: 6px 8px; margin-bottom: 8px;
  border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.sidebar ul { list-style: none; }
.sidebar li { margin-bottom: 2px; }
.sidebar a { display: block; padding: 4px 6px; text-decoration: none;
  color: #333; font-size: 13px; border-radius: 3px; }
.sidebar a:hover { background: #e8e8e8; }
.sidebar .nav-item.unanchored a { color: #6c757d; font-style: italic; }

.main { margin-left: 300px; padding: 24px 32px; max-width: 900px; flex: 1; }

.report-header h1 { font-size: 22px; margin-bottom: 4px; }
.report-header .versions { color: #666; font-size: 15px; margin-bottom: 16px; }
.summary-bar { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.summary-item { font-size: 14px; }
.summary-item strong { margin-right: 4px; }

.badge { display: inline-block; padding: 1px 6px; border-radius: 3px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-modified { background: #fff3cd; color: #856404; }
.badge-added { background: #d4edda; color: #155724; }
.badge-removed { background: #f8d7da; color: #721c24; }
.badge-moved { background: #cce5ff; color: #004085; }

.financial-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
.financial-table th { background: #f0f0f0; text-align: left; padding: 8px; border-bottom: 2px solid #ccc; }
.financial-table td { padding: 6px 8px; border-bottom: 1px solid #eee; }
.financial-table .amount { text-align: right; font-variant-numeric: tabular-nums; }
.financial-table a { color: #0056b3; text-decoration: none; }
.financial-table a:hover { text-decoration: underline; }
tr.increase .change-amount { color: #155724; }
tr.decrease .change-amount { color: #721c24; }
tr.unchanged .change-amount { color: #666; }

.change-card { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 16px;
  padding: 16px; background: #fff; }
.change-card.added { border-left: 4px solid #28a745; }
.change-card.removed { border-left: 4px solid #dc3545; }
.change-card.modified { border-left: 4px solid #ffc107; }
.change-card.moved { border-left: 4px solid #007bff; }
.change-card.unanchored { border-left: 4px solid #6c757d; background: #fafafa; }
.change-card.unanchored .change-header h3 {
  color: #6c757d; font-style: italic; font-weight: 400; }
.change-card.unanchored .change-header h3::before { content: "⚠ "; }

.change-header { margin-bottom: 6px; }
.change-header h3 { font-size: 16px; display: inline; margin-left: 8px; font-weight: 600; }

.citation { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px;
  color: #555; margin: 4px 0 12px; }
.citation .v1, .citation .v2 { display: inline-block; padding: 1px 6px;
  background: #f0f0f0; border-radius: 3px; margin-right: 6px; }
.citation .v1::before { content: "v1: "; color: #888; }
.citation .v2::before { content: "v2: "; color: #888; }

.change-body { font-size: 14px; line-height: 1.7; }
.added-text { background: #e6ffe6; padding: 10px; border-radius: 4px; }
.removed-text { background: #ffe6e6; padding: 10px; border-radius: 4px;
  text-decoration: line-through; color: #666; }
.old-text { background: #ffe6e6; padding: 8px; border-radius: 4px; margin-bottom: 8px; }
.new-text { background: #e6ffe6; padding: 8px; border-radius: 4px; }
.move-info { font-size: 13px; color: #004085; margin-bottom: 8px;
  padding: 6px 10px; background: #e7f1ff; border-radius: 3px; }
.move-info code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; }

del { background: #fecdd3; text-decoration: line-through; color: #9a3412; padding: 0 1px; }
ins { background: #bbf7d0; text-decoration: none; color: #166534; padding: 0 1px; }

.financial-callout { margin-top: 12px; padding: 10px 14px; background: #f0f7ff;
  border: 1px solid #b6d4fe; border-radius: 4px; font-size: 13px;
  font-variant-numeric: tabular-nums; }
.financial-callout .row { display: flex; gap: 10px; margin-bottom: 2px; }
.financial-callout .label { color: #555; min-width: 110px; }
.financial-callout .delta.decrease { color: #721c24; font-weight: 600; }
.financial-callout .delta.increase { color: #155724; font-weight: 600; }
.financial-callout .delta.unchanged { color: #555; }
.financial-callout .net { margin-top: 6px; padding-top: 6px;
  border-top: 1px solid #b6d4fe; font-weight: 600; }

.nav-buttons { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 8px; z-index: 10; }
.nav-buttons button { padding: 8px 14px; border: 1px solid #ccc; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.nav-buttons button:hover { background: #f0f0f0; }

@media print {
  .sidebar, .nav-buttons, #sidebar-filter { display: none; }
  .main { margin-left: 0; }
  .change-card { break-inside: avoid; }
}
"""


_JS = """\
document.addEventListener('DOMContentLoaded', function() {
  var filter = document.getElementById('sidebar-filter');
  if (filter) {
    filter.addEventListener('input', function() {
      var q = this.value.toLowerCase();
      document.querySelectorAll('.sidebar li').forEach(function(li) {
        li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }
  var cards = document.querySelectorAll('.change-card');
  var current = -1;
  function goTo(idx) {
    if (idx >= 0 && idx < cards.length) {
      current = idx;
      cards[idx].scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }
  var prev = document.getElementById('btn-prev');
  var next = document.getElementById('btn-next');
  if (prev) prev.addEventListener('click', function() { goTo(current - 1); });
  if (next) next.addEventListener('click', function() { goTo(current + 1); });
});
"""


def format_pdf_html(
    diff: PdfDiff,
    *,
    bill_type: str,
    bill_number: str | int,
    congress: int | str,
    v1_label: str = "v1",
    v2_label: str = "v2",
) -> str:
    """Assemble a complete standalone HTML report from a PdfDiff."""
    sidebar = _build_sidebar(diff)
    cards = "\n".join(_build_card(h, i, diff.v1_anchors, diff.v2_anchors) for i, h in enumerate(diff.hunks))
    financial = _build_financial_summary(diff)

    summary_items: list[str] = []
    summary = diff.summary
    for key in ("modified", "added", "removed", "moved"):
        count = summary.get(key, 0)
        if count > 0:
            summary_items.append(
                f'<span class="summary-item">'
                f'<span class="badge badge-{key}">{key}</span> '
                f"<strong>{count}</strong>"
                f"</span>"
            )

    bill_label = f"{escape(str(bill_type).upper())} {escape(str(bill_number))}"
    cards_section = cards if cards.strip() else '<p class="no-changes">No changes detected.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDF Diff: {bill_label}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="layout">
{sidebar}
<div class="main">
<div class="report-header">
<h1>{bill_label} &mdash; PDF Comparison</h1>
<div class="versions">{escape(v1_label)} &rarr; {escape(v2_label)} · {escape(str(congress))}th Congress</div>
<div class="summary-bar">{"".join(summary_items)}</div>
</div>
{financial}
<h2>Changes</h2>
{cards_section}
</div>
</div>
<div class="nav-buttons">
<button id="btn-prev">&larr; Prev</button>
<button id="btn-next">Next &rarr;</button>
</div>
<script>
{_JS}
</script>
</body>
</html>"""
