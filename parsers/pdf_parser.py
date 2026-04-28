"""PDF backend for ``parsers.load_bill_tree``.

Built incrementally across Phase B0-B8. This commit (B0) establishes
the module skeleton and deterministic character extraction; later
phases add line reconstruction, classification, and tree construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bill_tree import BillTree

Char = dict[str, Any]
Line = dict[str, Any]

# Horizontal gap (in pdfplumber px units) that distinguishes a margin
# line-number from a digit that's part of legislative content. Real GPO
# line-number gaps are ~10-45px (body column starts past the line-number
# margin); kerned digit-letter pairs within a word like "21st" are ~0-2px.
_LINE_NUMBER_GAP_THRESHOLD = 5.0


def _metadata_from_path(pdf_path: Path) -> tuple[int, str, int, str]:
    """Derive ``(congress, bill_type, bill_number, version)`` from path layout.

    Expected layout: ``<corpus>/<congress>-<bill_type>-<bill_number>/<idx>_<slug>.pdf``.
    Components that don't parse fall back to zeros / empty strings rather
    than raising — the caller still gets a usable ``BillTree`` even when
    the file lives outside the corpus convention.
    """
    parent = pdf_path.parent.name
    congress = 0
    bill_type = ""
    bill_number = 0
    parts = parent.split("-")
    if len(parts) >= 3 and parts[0].isdigit() and parts[-1].isdigit():
        try:
            congress = int(parts[0])
            bill_type = "-".join(parts[1:-1])
            bill_number = int(parts[-1])
        except ValueError:
            pass

    version = ""
    stem_parts = pdf_path.stem.split("_", 1)
    if len(stem_parts) == 2:
        version = stem_parts[1]
    return congress, bill_type, bill_number, version


def _sort_chars(chars: list[Char]) -> list[Char]:
    """Sort chars deterministically by ``(round(top, 1), round(x0, 1), text)``.

    Defeats pdfminer.six iteration-order differences so any downstream
    ``synth_id`` / ``match_path`` outputs are byte-for-byte stable
    across runs and platforms.
    """
    return sorted(
        chars,
        key=lambda c: (
            round(c.get("top", 0.0), 1),
            round(c.get("x0", 0.0), 1),
            c.get("text", ""),
        ),
    )


def _extract_pages(pdf_path: Path) -> tuple[list[list[Char]], list[float]]:
    """Read each page's chars and height from ``pdf_path``.

    Each page's chars are sorted via :func:`_sort_chars` before
    return, so the output is deterministic. Returns a tuple of
    ``(pages, heights)`` parallel-indexed.
    """
    import pdfplumber

    pages: list[list[Char]] = []
    heights: list[float] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(_sort_chars(list(page.chars)))
            heights.append(float(page.height))
    return pages, heights


def _finalize_line(chars: list[Char]) -> Line:
    """Build a line summary dict from a list of chars (re-sorted by ``x0``)."""
    chars_sorted = sorted(chars, key=lambda c: float(c.get("x0", 0.0)))
    text = "".join(c.get("text", "") for c in chars_sorted)
    if not chars_sorted:
        return {"text": "", "top": 0.0, "x0": 0.0, "x1": 0.0, "chars": []}
    return {
        "text": text,
        "top": float(chars_sorted[0].get("top", 0.0)),
        "x0": float(chars_sorted[0].get("x0", 0.0)),
        "x1": max(float(c.get("x1", c.get("x0", 0.0))) for c in chars_sorted),
        "chars": chars_sorted,
    }


def _group_into_lines(chars: list[Char]) -> list[Line]:
    """Group chars into lines using a font-size-aware tolerance.

    Tolerance per pair = ``max(2.0, 0.4 * max(line_max_size, char.size))``.
    The ``0.4 * size`` term handles the common GPO case where small-caps
    continuation chars have a ``top`` ~3px below their lead-cap baseline
    (because pdfplumber's ``top`` is bounding-box top, not baseline, and
    smaller chars have smaller bounding boxes).

    Chars are sorted by ``top`` ascending, so each char's only join
    candidate is the most-recently-opened line. Lines are returned in
    y-order with their chars sorted by ``x0``.
    """
    pending: list[list[Char]] = []
    sorted_chars = sorted(
        chars,
        key=lambda c: (round(float(c.get("top", 0.0)), 1), float(c.get("x0", 0.0))),
    )
    for ch in sorted_chars:
        ch_top = float(ch.get("top", 0.0))
        ch_size = float(ch.get("size", 0.0))
        if pending:
            cur = pending[-1]
            cur_max_size = max(float(c.get("size", 0.0)) for c in cur)
            tol = max(2.0, 0.4 * max(cur_max_size, ch_size))
            cur_mean_top = sum(float(c["top"]) for c in cur) / len(cur)
            if abs(ch_top - cur_mean_top) <= tol:
                cur.append(ch)
                continue
        pending.append([ch])
    return [_finalize_line(c_list) for c_list in pending]


def _looks_like_small_caps_continuation(prev: Line, nxt: Line) -> bool:
    """True if ``nxt`` is a small-caps continuation of ``prev``.

    All four conditions must hold:

    - ``prev`` ends with a single uppercase alpha letter (the lead cap).
    - That lead char's ``size`` is strictly larger than every ``nxt`` char.
    - Every ``nxt`` char is uppercase alpha at ``size <= 0.8 * lead_size``.
    - ``nxt.x0`` sits within +/- 5px of ``prev.x1`` (continuation, not wrap).
    """
    prev_chars = prev.get("chars") or []
    nxt_chars = nxt.get("chars") or []
    if not prev_chars or not nxt_chars:
        return False
    last = prev_chars[-1]
    last_text = last.get("text", "")
    if not (len(last_text) == 1 and last_text.isalpha() and last_text.isupper()):
        return False
    lead_size = float(last.get("size", 0.0))
    if lead_size <= 0.0:
        return False
    threshold = 0.8 * lead_size
    for c in nxt_chars:
        t = c.get("text", "")
        if not (t.isalpha() and t.isupper()):
            return False
        if float(c.get("size", 0.0)) > threshold:
            return False
    return abs(float(nxt["x0"]) - float(prev["x1"])) <= 5.0


def _reattach_small_caps(lines: list[Line]) -> list[Line]:
    """Merge small-caps continuation lines into their lead-cap parent.

    Defensive pass for cases where the baseline gap exceeds the dynamic
    tolerance in :func:`_group_into_lines` (e.g., 18pt heading + 10pt
    small caps yields a ~12-15px gap). For typical 12-14pt sizes the
    grouping function bridges these splits and this pass is a no-op.

    Cascades correctly: if line N+2 is also a continuation of the merged
    N+(N+1), it gets folded in as well.
    """
    if len(lines) < 2:
        return lines
    out: list[Line] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        j = i + 1
        while j < len(lines) and _looks_like_small_caps_continuation(cur, lines[j]):
            cur = _finalize_line(cur["chars"] + lines[j]["chars"])
            j += 1
        out.append(cur)
        i = j
    return out


def _strip_line_number_prefix(line: Line) -> Line:
    """Strip a glued line-number digit run from the start of a line.

    GPO bills typeset line numbers in the lower-left margin (x0 ~ 126-133)
    on the same y-baseline as the body text, so pdfplumber merges them
    into the line as e.g. ``7TITLE I``, ``21SEC. 101.``, ``4erwise made``,
    or ``10(b)``. The robust discriminator is the HORIZONTAL GAP between
    the last digit and the first non-digit char: line numbers always have
    a gap of >= ~10px (body column begins past the margin), while a
    digit-prefix that's part of legitimate content like ``21st Century
    Cures Act`` is rendered with normal kerning (gap ~ 0-2px).

    Returns the input line unchanged if it has no leading digits, or if
    the digit run isn't followed by a wide-enough gap.
    """
    chars = line.get("chars", [])
    digit_count = 0
    for c in chars:
        if c.get("text", "").isdigit():
            digit_count += 1
        else:
            break
    if digit_count == 0 or digit_count >= len(chars):
        return line
    last_digit_x1 = float(chars[digit_count - 1].get("x1", 0.0))
    next_char_x0 = float(chars[digit_count].get("x0", 0.0))
    if (next_char_x0 - last_digit_x1) < _LINE_NUMBER_GAP_THRESHOLD:
        return line
    return _finalize_line(chars[digit_count:])


def _strip_line_numbers(lines: list[Line]) -> list[Line]:
    """Apply :func:`_strip_line_number_prefix` to every line in ``lines``."""
    return [_strip_line_number_prefix(ln) for ln in lines]


def parse_pdf(pdf_path: Path) -> BillTree:
    """Parse a PDF bill into a ``BillTree``.

    Phase B0 only: extracts and sorts chars deterministically, derives
    bill metadata from the path, and returns an empty tree. Subsequent
    phases populate the nodes:

    - B1: font-size-aware line reconstruction (small-caps reattach)
    - B2: line-number stripping
    - B3: cover-page / preamble guard
    - B4: multi-line TITLE / DIVISION header join
    - B5: body wrap and conservative dehyphenation
    - B6: cross-page continuity
    - B7: walker-compatible structural emission
    - B8: orphan handling
    """
    _pages, _heights = _extract_pages(pdf_path)
    congress, bill_type, bill_number, version = _metadata_from_path(pdf_path)
    return BillTree(congress, bill_type, bill_number, version, [])
