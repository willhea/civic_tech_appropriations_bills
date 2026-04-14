"""Generate a standalone HTML report from a bill diff dict."""

import difflib
from html import escape


def word_diff(old_text: str, new_text: str, threshold: float = 0.4) -> str | None:
    """Produce an inline HTML diff at the word level.

    Returns an HTML string with <del> and <ins> tags wrapping changed words,
    or None if the texts are too dissimilar (below *threshold*).
    """
    old_words = old_text.split()
    new_words = new_text.split()

    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    if matcher.ratio() < threshold:
        return None

    parts: list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            parts.append(escape(" ".join(old_words[i1:i2])))
        elif op == "replace":
            parts.append("<del>" + escape(" ".join(old_words[i1:i2])) + "</del>")
            parts.append("<ins>" + escape(" ".join(new_words[j1:j2])) + "</ins>")
        elif op == "delete":
            parts.append("<del>" + escape(" ".join(old_words[i1:i2])) + "</del>")
        elif op == "insert":
            parts.append("<ins>" + escape(" ".join(new_words[j1:j2])) + "</ins>")

    return " ".join(parts)


def _version_label(name: str, number: int | None) -> str:
    """Format a version label, optionally prefixed with 'v1:', 'v2:', etc."""
    if number is not None:
        return f"v{number}: {name}"
    return name


def _fmt_dollar(amount: int) -> str:
    """Format an integer as a dollar string with commas."""
    return f"${amount:,}"


def _fmt_change(old: int, new: int) -> tuple[str, str, str]:
    """Return (change_dollar, change_pct, css_class) for an amount pair."""
    diff = new - old
    sign = "+" if diff >= 0 else ""
    dollar = f"{sign}{_fmt_dollar(diff)}" if diff >= 0 else f"-{_fmt_dollar(abs(diff))}"
    if old != 0:
        pct = f"{sign}{diff / old * 100:.1f}%"
    else:
        pct = "\u2014"
    css = "increase" if diff > 0 else "decrease" if diff < 0 else "unchanged"
    return dollar, pct, css


def build_financial_table(changes: list[dict]) -> str:
    """Build an HTML financial summary table from change dicts.

    Only includes changes that have financial data with amounts_changed=True.
    Returns an empty string if there are no financial changes.
    """
    rows: list[dict] = []
    for i, change in enumerate(changes):
        fin = change.get("financial")
        if not fin or not fin.get("amounts_changed"):
            continue
        path_parts = change.get("display_path_new") or change.get("display_path_old") or []
        path = escape(" &gt; ".join(path_parts))
        section = escape(change.get("section_number", "") or "")
        # Use paired_amounts if available, fall back to positional pairing
        paired = fin.get("paired_amounts")
        if paired:
            amount_pairs = [(p[0], p[1]) for p in paired]
        else:
            old_amounts = fin.get("old_amounts", [])
            new_amounts = fin.get("new_amounts", [])
            max_len = max(len(old_amounts), len(new_amounts))
            amount_pairs = [
                (old_amounts[j] if j < len(old_amounts) else None,
                 new_amounts[j] if j < len(new_amounts) else None)
                for j in range(max_len)
            ]
        rows.append({
            "index": i,
            "path": path,
            "section": section,
            "amount_pairs": amount_pairs,
        })

    if not rows:
        return ""

    lines = [
        '<table class="financial-table">',
        "<thead><tr>",
        "<th>Section</th>",
        "<th>Old Amount</th>",
        "<th>New Amount</th>",
        "<th>Change ($)</th>",
        "<th>Change (%)</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for row in rows:
        amount_pairs = row["amount_pairs"]
        num_pairs = len(amount_pairs)

        for j, (old_val, new_val) in enumerate(amount_pairs):
            old_str = _fmt_dollar(old_val) if old_val is not None else "\u2014"
            new_str = _fmt_dollar(new_val) if new_val is not None else "\u2014"

            if old_val is not None and new_val is not None:
                change_dollar, change_pct, css = _fmt_change(old_val, new_val)
            elif new_val is not None:
                change_dollar = f"+{_fmt_dollar(new_val)}"
                change_pct = "\u2014"
                css = "increase"
            elif old_val is not None:
                change_dollar = f"-{_fmt_dollar(old_val)}"
                change_pct = "\u2014"
                css = "decrease"
            else:
                continue

            # Show path only on first sub-row
            if j == 0:
                rowspan = f' rowspan="{num_pairs}"' if num_pairs > 1 else ""
                path_cell = f'<td{rowspan}><a href="#change-{row["index"]}">{row["path"]}</a></td>'
            else:
                path_cell = ""

            lines.append(
                f'<tr class="{css}">'
                f'{path_cell}'
                f'<td class="amount">{old_str}</td>'
                f'<td class="amount">{new_str}</td>'
                f'<td class="amount">{change_dollar}</td>'
                f'<td class="amount">{change_pct}</td>'
                f'</tr>'
            )

    lines.append("</tbody></table>")
    return "\n".join(lines)


def _display_path(change: dict) -> str:
    """Return the best display path for a change, joined with ' > '."""
    parts = change.get("display_path_new") or change.get("display_path_old") or []
    return " &gt; ".join(escape(p) for p in parts)


def _financial_callout(financial: dict) -> str:
    """Render a financial callout box for a change card."""
    # Use paired_amounts if available, fall back to positional pairing
    paired = financial.get("paired_amounts")
    if paired:
        amount_pairs = [(p[0], p[1]) for p in paired]
    else:
        old_amounts = financial.get("old_amounts", [])
        new_amounts = financial.get("new_amounts", [])
        max_len = max(len(old_amounts), len(new_amounts), 1)
        amount_pairs = [
            (old_amounts[i] if i < len(old_amounts) else None,
             new_amounts[i] if i < len(new_amounts) else None)
            for i in range(max_len)
        ]

    rows = []
    for old_val, new_val in amount_pairs:
        old_str = _fmt_dollar(old_val) if old_val is not None else "\u2014"
        new_str = _fmt_dollar(new_val) if new_val is not None else "\u2014"

        if old_val is not None and new_val is not None:
            change_str, _, _ = _fmt_change(old_val, new_val)
        elif new_val is not None:
            change_str = f"+{_fmt_dollar(new_val)}"
        elif old_val is not None:
            change_str = f"-{_fmt_dollar(old_val)}"
        else:
            continue
        rows.append(f"<div>{old_str} &rarr; {new_str} ({change_str})</div>")

    return f'<div class="financial-callout">{"".join(rows)}</div>'


def build_change_card(change: dict, index: int) -> str:
    """Render a single change as an HTML card."""
    change_type = change.get("change_type", "modified")
    path = _display_path(change)
    section = escape(change.get("section_number", "") or "")
    old_text = change.get("old_text") or ""
    new_text = change.get("new_text") or ""

    parts = [f'<div class="change-card {change_type}" id="change-{index}">']

    # Header
    parts.append(f'<div class="change-header">')
    parts.append(f'<span class="badge badge-{change_type}">{escape(change_type)}</span>')
    parts.append(f'<h3>{path}</h3>')
    if section:
        parts.append(f'<span class="section-number">{section}</span>')
    parts.append('</div>')

    # Body
    if change_type == "modified":
        diff_html = word_diff(old_text, new_text)
        if diff_html is not None:
            parts.append(f'<div class="change-body diff-inline">{diff_html}</div>')
        else:
            parts.append(f'<div class="change-body">')
            parts.append(f'<div class="old-text">{escape(old_text)}</div>')
            parts.append(f'<div class="new-text">{escape(new_text)}</div>')
            parts.append('</div>')
    elif change_type == "added":
        parts.append(f'<div class="change-body added-text">{escape(new_text)}</div>')
    elif change_type == "removed":
        parts.append(f'<div class="change-body removed-text">{escape(old_text)}</div>')
    elif change_type == "moved":
        old_path_parts = change.get("display_path_old") or []
        new_path_parts = change.get("display_path_new") or []
        old_path = " &gt; ".join(escape(p) for p in old_path_parts)
        new_path = " &gt; ".join(escape(p) for p in new_path_parts)
        parts.append(f'<div class="move-info">Moved: {old_path} &rarr; {new_path}</div>')
        if old_text != new_text:
            diff_html = word_diff(old_text, new_text)
            if diff_html is not None:
                parts.append(f'<div class="change-body diff-inline">{diff_html}</div>')
            else:
                parts.append(f'<div class="change-body">')
                parts.append(f'<div class="old-text">{escape(old_text)}</div>')
                parts.append(f'<div class="new-text">{escape(new_text)}</div>')
                parts.append('</div>')

    # Financial callout
    fin = change.get("financial")
    if fin and fin.get("amounts_changed"):
        parts.append(_financial_callout(fin))

    parts.append('</div>')
    return "\n".join(parts)


def build_sidebar(changes: list[dict]) -> str:
    """Build a sidebar navigation listing all changes."""
    items: list[str] = []
    for i, change in enumerate(changes):
        change_type = change.get("change_type", "modified")
        path_parts = change.get("display_path_new") or change.get("display_path_old") or []
        label = escape(" > ".join(path_parts)) if path_parts else "(unknown)"
        section = escape(change.get("section_number", "") or "")
        if section:
            label = f"{section} — {label}"

        items.append(
            f'<li class="nav-item" data-type="{change_type}">'
            f'<a href="#change-{i}">'
            f'<span class="badge badge-{change_type}">{change_type}</span> '
            f'{label}'
            f'</a></li>'
        )

    return (
        '<nav class="sidebar">\n'
        '<input type="text" id="sidebar-filter" placeholder="Filter sections...">\n'
        f'<ul>{"".join(items)}</ul>\n'
        '</nav>'
    )


_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, 'Times New Roman', serif; color: #222; line-height: 1.6; }
.layout { display: flex; min-height: 100vh; }

/* Sidebar */
.sidebar { width: 300px; position: fixed; top: 0; left: 0; height: 100vh;
  overflow-y: auto; background: #f7f7f7; border-right: 1px solid #ddd; padding: 12px; }
.sidebar input { width: 100%; padding: 6px 8px; margin-bottom: 8px;
  border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.sidebar ul { list-style: none; }
.sidebar li { margin-bottom: 2px; }
.sidebar a { display: block; padding: 4px 6px; text-decoration: none;
  color: #333; font-size: 13px; border-radius: 3px; }
.sidebar a:hover { background: #e8e8e8; }

/* Main content */
.main { margin-left: 300px; padding: 24px 32px; max-width: 900px; flex: 1; }

/* Header */
.report-header h1 { font-size: 22px; margin-bottom: 4px; }
.report-header .versions { color: #666; font-size: 15px; margin-bottom: 16px; }
.summary-bar { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.summary-item { font-size: 14px; }
.summary-item strong { margin-right: 4px; }

/* Badges */
.badge { display: inline-block; padding: 1px 6px; border-radius: 3px;
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-modified { background: #fff3cd; color: #856404; }
.badge-added { background: #d4edda; color: #155724; }
.badge-removed { background: #f8d7da; color: #721c24; }
.badge-moved { background: #cce5ff; color: #004085; }

/* Financial table */
.financial-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
.financial-table th { background: #f0f0f0; text-align: left; padding: 8px; border-bottom: 2px solid #ccc; }
.financial-table td { padding: 6px 8px; border-bottom: 1px solid #eee; }
.financial-table .amount { text-align: right; font-variant-numeric: tabular-nums; }
.financial-table a { color: #0056b3; text-decoration: none; }
.financial-table a:hover { text-decoration: underline; }
tr.increase .amount:nth-child(4), tr.increase .amount:nth-child(5) { color: #155724; }
tr.decrease .amount:nth-child(4), tr.decrease .amount:nth-child(5) { color: #721c24; }

/* Change cards */
.change-card { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 16px;
  padding: 16px; background: #fff; }
.change-card.added { border-left: 4px solid #28a745; }
.change-card.removed { border-left: 4px solid #dc3545; }
.change-card.modified { border-left: 4px solid #ffc107; }
.change-card.moved { border-left: 4px solid #007bff; }
.change-header { margin-bottom: 12px; }
.change-header h3 { font-size: 16px; display: inline; margin-left: 8px; }
.section-number { display: block; font-size: 13px; color: #666; margin-top: 2px; }
.change-body { font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
.added-text { background: #e6ffe6; padding: 8px; border-radius: 4px; }
.removed-text { background: #ffe6e6; padding: 8px; border-radius: 4px; text-decoration: line-through; color: #666; }
.old-text { background: #ffe6e6; padding: 8px; border-radius: 4px; margin-bottom: 8px; }
.new-text { background: #e6ffe6; padding: 8px; border-radius: 4px; }
.move-info { font-size: 13px; color: #004085; margin-bottom: 8px; }

/* Inline diff */
del { background: #fecdd3; text-decoration: line-through; color: #9a3412; }
ins { background: #bbf7d0; text-decoration: none; color: #166534; }

/* Financial callout */
.financial-callout { margin-top: 10px; padding: 8px 12px; background: #f0f7ff;
  border: 1px solid #b6d4fe; border-radius: 4px; font-size: 13px; }

/* Navigation buttons */
.nav-buttons { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 8px; z-index: 10; }
.nav-buttons button { padding: 8px 14px; border: 1px solid #ccc; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.nav-buttons button:hover { background: #f0f0f0; }

/* Print */
@media print {
  .sidebar, .nav-buttons, #sidebar-filter { display: none; }
  .main { margin-left: 0; }
  .change-card { break-inside: avoid; }
}
"""

_JS = """\
document.addEventListener('DOMContentLoaded', function() {
  // Sidebar filter
  var filter = document.getElementById('sidebar-filter');
  if (filter) {
    filter.addEventListener('input', function() {
      var q = this.value.toLowerCase();
      document.querySelectorAll('.sidebar li').forEach(function(li) {
        li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  // Prev/next navigation
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

  // Financial table sort
  document.querySelectorAll('.financial-table th').forEach(function(th, colIdx) {
    th.style.cursor = 'pointer';
    th.addEventListener('click', function() {
      var table = th.closest('table');
      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      var asc = th.dataset.sort !== 'asc';
      th.dataset.sort = asc ? 'asc' : 'desc';
      rows.sort(function(a, b) {
        var aVal = a.cells[colIdx] ? a.cells[colIdx].textContent.replace(/[^\\d.-]/g, '') : '';
        var bVal = b.cells[colIdx] ? b.cells[colIdx].textContent.replace(/[^\\d.-]/g, '') : '';
        var aNum = parseFloat(aVal), bNum = parseFloat(bVal);
        if (!isNaN(aNum) && !isNaN(bNum)) return asc ? aNum - bNum : bNum - aNum;
        return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      });
      rows.forEach(function(row) { tbody.appendChild(row); });
    });
  });
});
"""


def format_html(diff_dict: dict) -> str:
    """Assemble a complete standalone HTML report from a bill diff dict."""
    bill_type = escape(diff_dict.get("bill_type", "").upper())
    bill_number = diff_dict.get("bill_number", "")
    congress = diff_dict.get("congress", "")
    old_version = escape(diff_dict.get("old_version", ""))
    new_version = escape(diff_dict.get("new_version", ""))
    old_version_num = diff_dict.get("old_version_number")
    new_version_num = diff_dict.get("new_version_number")
    summary = diff_dict.get("summary", {})
    changes = diff_dict.get("changes", [])

    # Build components
    sidebar = build_sidebar(changes)
    financial_table = build_financial_table(changes)
    cards = "\n".join(build_change_card(c, i) for i, c in enumerate(changes))

    # Summary bar
    summary_items = []
    for key in ("added", "removed", "modified", "moved"):
        count = summary.get(key, 0)
        if count > 0:
            summary_items.append(
                f'<span class="summary-item">'
                f'<span class="badge badge-{key}">{key}</span> '
                f'<strong>{count}</strong>'
                f'</span>'
            )

    financial_section = ""
    if financial_table:
        financial_section = (
            '<h2>Financial Summary</h2>\n'
            f'{financial_table}\n'
        )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bill Comparison: {bill_type} {bill_number}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="layout">
{sidebar}
<div class="main">
<div class="report-header">
<h1>{bill_type} {bill_number} &mdash; Bill Comparison</h1>
<div class="versions">{_version_label(old_version, old_version_num)} &rarr; {_version_label(new_version, new_version_num)} &middot; {congress}th Congress</div>
<div class="summary-bar">{"".join(summary_items)}</div>
</div>
{financial_section}
<h2>Changes</h2>
{cards if cards.strip() else '<p class="no-changes">No changes found between these versions.</p>'}
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
