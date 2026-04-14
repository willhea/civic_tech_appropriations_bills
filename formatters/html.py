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
        old_amounts = fin.get("old_amounts", [])
        new_amounts = fin.get("new_amounts", [])
        path_parts = change.get("display_path_new") or change.get("display_path_old") or []
        path = escape(" &gt; ".join(path_parts))
        section = escape(change.get("section_number", "") or "")
        rows.append({
            "index": i,
            "path": path,
            "section": section,
            "old_amounts": old_amounts,
            "new_amounts": new_amounts,
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
        old_amounts = row["old_amounts"]
        new_amounts = row["new_amounts"]
        max_len = max(len(old_amounts), len(new_amounts))

        for j in range(max_len):
            old_val = old_amounts[j] if j < len(old_amounts) else None
            new_val = new_amounts[j] if j < len(new_amounts) else None

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
                rowspan = f' rowspan="{max_len}"' if max_len > 1 else ""
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
