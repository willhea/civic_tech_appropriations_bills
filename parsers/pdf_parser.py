"""PDF backend for ``parsers.load_bill_tree``.

Built incrementally across Phase B0-B8. This commit (B0) establishes
the module skeleton and deterministic character extraction; later
phases add line reconstruction, classification, and tree construction.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from bill_tree import BillTree, normalize_bill_from_root

from . import classifier as cls
from . import synthetic_xml as syx

Char = dict[str, Any]
Line = dict[str, Any]

# Horizontal gap (in pdfplumber px units) that distinguishes a margin
# line-number from a digit that's part of legislative content. Real GPO
# line-number gaps are ~10-45px (body column starts past the line-number
# margin); kerned digit-letter pairs within a word like "21st" are ~0-2px.
_LINE_NUMBER_GAP_THRESHOLD = 5.0

# Standard GPO enacting clause -- always the last sentence of the
# cover-page preamble. Match case-insensitively because some bills use
# all-caps stylings.
_ENACTING_CLAUSE_RE = re.compile(r"Be it enacted by the Senate", re.IGNORECASE)

# Fallback structural markers for drafts / committee prints that lack
# the standard enacting clause. We anchor the body at the first
# DIVISION / TITLE / SEC. line within the scan window.
_STRUCTURAL_MARKER_RE = re.compile(r"^(?:DIVISION|TITLE)\s+\S+|^SEC(?:TION|\.)\s")

# How many lines from the start to scan for the enacting clause / fallback
# marker. Real bills hit one or the other within the first 30-50 lines.
_MAX_PREAMBLE_SCAN_LINES = 100

# Enum-only TITLE / DIVISION line ("TITLE I", "DIVISION A", "TITLE 5").
# When pdfplumber outputs the heading split across lines (enum on one,
# name on subsequent), this matches the enum line; B4 scans forward for
# the name continuation.
_ENUM_ONLY_HEADING_RE = re.compile(r"^(TITLE|DIVISION)\s+([A-Z]+|\d+)\s*$")

# A heading-name line "continues" onto the next line when it ends with a
# trailing hyphen (word-wrap), comma (list continues), or " AND" / " OR"
# (Oxford-comma list final item not yet seen). A line ending in any other
# token terminates the heading.
_HEADING_CONTINUES_RE = re.compile(r"(?:[-,]|\b(?:AND|OR))\s*$")

# Hard cap on continuation lines so a runaway scan can't eat the rest of
# the bill. Real GPO headings span 1-4 lines; 6 is generous.
_MAX_HEADING_CONTINUATION_LINES = 6

# Page-chrome stripping (B6): the top and bottom bands (in pdfplumber px)
# treated as candidates for headers / footers / page numbers. A line whose
# ``top`` falls within either band gets evaluated for chrome-stripping;
# lines in the body band are always preserved.
_HEADER_BAND_PX = 60.0
_FOOTER_BAND_PX = 60.0

# Repetition threshold: a line whose normalized text appears in the same
# band on >= this fraction of pages is treated as repeated chrome and
# stripped from every page where it occurs. The minimum-2 floor prevents
# a single page from misclassifying its only header/footer line.
_CHROME_REPETITION_FRACTION = 0.5

_PAGE_NUMBER_ONLY_RE = re.compile(r"^\s*\d+\s*$")

# Body-line dehyphenation rule: drop end-of-line ``-`` only when the chars
# immediately before AND after the hyphen are both lowercase letters. This
# recovers the common word-wrap case (``Representa-/tives`` -> ``Representatives``,
# ``oth-/erwise`` -> ``otherwise``) while preserving compounds with an
# uppercase next word (``non-/Federal``) or a punctuation-bearing prev
# (``U.S.-/Mexico``).
#
# Known trade-off: prefix-compounds like ``re-/enacted`` and
# ``pre-/decisional`` get glued to ``reenacted`` / ``predecisional`` when
# they happen to wrap exactly at the prefix-hyphen. Real word-wraps are
# many times more frequent than prefix-compound wraps in bill body text,
# and the 1-character glue artifact is absorbed by the body_similarity
# metric. A more accurate fix would require a hyphenation dictionary
# (pyphen + a wordlist for legal jargon), which is out of scope here.


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


def _split_preamble_and_body(lines: list[Line]) -> tuple[list[Line], list[Line]]:
    """Split ``lines`` into ``(preamble, body)`` at the bill's structural start.

    Primary anchor: the enacting clause ``Be it enacted by the Senate ...``
    (always the last sentence of a published bill's cover-page preamble).
    Everything up to and including that line goes into the preamble;
    everything after into the body. Only the FIRST occurrence anchors —
    a stray reference deep in the body doesn't re-split.

    Fallback (drafts, committee prints, anything missing the enacting
    clause): scan the first ``_MAX_PREAMBLE_SCAN_LINES`` lines for a
    structural marker (``DIVISION X``, ``TITLE I``, ``SEC. 101``, etc.).
    Drop everything before the marker; the marker itself is the first
    body line.

    Last resort: neither anchor visible -> ``([], lines)``. The state
    machine's no-open-leaf behavior absorbs cover-page leaks at that
    point; we'd rather under-strip than throw away real content.
    """
    for i, ln in enumerate(lines):
        if _ENACTING_CLAUSE_RE.search(ln.get("text", "")):
            return lines[: i + 1], lines[i + 1 :]

    scan_limit = min(_MAX_PREAMBLE_SCAN_LINES, len(lines))
    for i in range(scan_limit):
        if _STRUCTURAL_MARKER_RE.match(lines[i].get("text", "").strip()):
            return lines[:i], lines[i:]

    return [], list(lines)


def _join_heading_continuation(parts: list[str]) -> str:
    """Concatenate continuation lines into a single heading string.

    Drops a trailing ``-`` at a line break (so ``INTEL-``/``LIGENCE``
    rejoins as ``INTELLIGENCE``); otherwise inserts a single space.
    """
    if not parts:
        return ""
    result = parts[0].rstrip()
    for raw in parts[1:]:
        p = raw.strip()
        if not p:
            continue
        if result.endswith("-"):
            result = result[:-1] + p
        else:
            result = result + " " + p
    return result


def _heading_continues(text: str) -> bool:
    """True if a heading-name line's last token suggests more text follows
    on the next line: trailing hyphen (word-wrap), comma, or ``AND`` /
    ``OR`` (list final item not yet seen)."""
    return bool(_HEADING_CONTINUES_RE.search(text.rstrip()))


def _join_multi_line_titles(lines: list[Line]) -> list[Line]:
    """Reassemble TITLE / DIVISION headings whose name sits on separate
    physical lines from the enum.

    GPO renders::

        TITLE I
        DEPARTMENTAL MANAGEMENT, INTEL-
        LIGENCE, SITUATIONAL AWARENESS, AND
        OVERSIGHT
        For necessary expenses...

    The classifier needs ``TITLE I — DEPARTMENTAL MANAGEMENT, INTELLIGENCE,
    SITUATIONAL AWARENESS, AND OVERSIGHT`` on a single line to emit the
    title's match_path. This function walks forward from each enum-only
    TITLE / DIVISION line, collecting all-uppercase continuation lines.

    Stop conditions (whichever fires first):

    - Next line is blank AND we've already collected at least one part
      (paragraph break ends the heading).
    - Next line matches a new structural marker (DIVISION, TITLE, SEC.).
    - Next line is not all-uppercase (mixed-case body text follows).
    - We've already collected a part AND that previous part doesn't end
      with a continuation token (``-``, ``,``, ``AND``, ``OR``). This
      catches the common case where one heading's name terminates and
      the next line is the start of a *new* all-uppercase heading.
    - Hard cap of ``_MAX_HEADING_CONTINUATION_LINES`` to bound runaway.

    A trailing ``-`` at a line break is dehyphenated at the join.
    """
    out: list[Line] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        text = ln.get("text", "").strip()
        m = _ENUM_ONLY_HEADING_RE.match(text)
        if not m:
            out.append(ln)
            i += 1
            continue
        kind, enum = m.group(1), m.group(2)
        name_parts: list[str] = []
        j = i + 1
        crossed_blank = False
        while j < len(lines) and len(name_parts) < _MAX_HEADING_CONTINUATION_LINES:
            next_text = lines[j].get("text", "").strip()
            if not next_text:
                crossed_blank = True
                j += 1
                continue
            if _STRUCTURAL_MARKER_RE.match(next_text):
                break
            if not cls.is_all_caps(next_text):
                break
            if name_parts:
                if crossed_blank:
                    break
                if not _heading_continues(name_parts[-1]):
                    break
            name_parts.append(next_text)
            j += 1
            crossed_blank = False
        if name_parts:
            joined_name = _join_heading_continuation(name_parts)
            new_line = dict(ln)
            new_line["text"] = f"{kind} {enum} — {joined_name}"
            out.append(new_line)
            i = j
        else:
            out.append(ln)
            i += 1
    return out


def _join_with_dehyphenation(prev: str, next_part: str) -> str:
    """Join two adjacent body-line texts, dehyphenating at end-of-line
    when both adjacent chars are lowercase letters.

    Rule: when ``prev`` ends with ``-``, drop the hyphen iff the char
    immediately before it AND the first char of ``next_part`` are both
    lowercase letters. Otherwise keep the hyphen and join with no space.
    When ``prev`` doesn't end with ``-``, join with a single space.

    This produces clean text on the common word-wrap case (``Representa-``
    + ``tives`` -> ``Representatives``) and preserves compounds like
    ``non-Federal`` (uppercase next) and ``U.S.-Mexico`` (punctuation
    before hyphen). Prefix-compounds that happen to wrap at the
    prefix-hyphen (``re-`` + ``enacted``) get glued (``reenacted``);
    accepted as documented above.
    """
    prev_r = prev.rstrip()
    next_l = next_part.lstrip()
    if not next_l:
        return prev_r
    if not prev_r:
        return next_l
    if prev_r.endswith("-"):
        before_hyphen = prev_r[:-1]
        if before_hyphen and before_hyphen[-1].islower() and next_l[0].islower():
            return before_hyphen + next_l
        return prev_r + next_l
    return prev_r + " " + next_l


def _join_body_lines(parts: list[str]) -> str:
    """Concatenate body-line texts into a single string with conservative
    dehyphenation at line breaks. Empty / whitespace-only parts are skipped.
    """
    if not parts:
        return ""
    result = ""
    for p in parts:
        if not p.strip():
            continue
        if not result:
            result = p.strip()
        else:
            result = _join_with_dehyphenation(result, p)
    return result


def _band_for_line(line: Line, page_height: float) -> str | None:
    """Classify a line's vertical position as ``"header"``, ``"footer"``,
    or ``None`` (body band)."""
    top = float(line.get("top", 0.0))
    if top <= _HEADER_BAND_PX:
        return "header"
    if page_height > 0 and top >= page_height - _FOOTER_BAND_PX:
        return "footer"
    return None


def _strip_page_chrome(pages_lines: list[list[Line]], page_heights: list[float]) -> list[list[Line]]:
    """Strip page chrome (footers, running headers, page numbers) from
    each page's line list.

    Two filters applied in a single pass:

    1. **Standalone numerics in the chrome band.** A line whose text is
       just a digit run (``"1"``, ``"42"``, ...) and whose ``top`` falls
       in the header or footer band is treated as a page number and
       dropped. Fires regardless of repetition count.
    2. **Lines repeating across pages within the same band.** A line
       whose normalized (whitespace-collapsed, lower-cased) text appears
       in the same band on at least
       ``max(2, ceil(N * _CHROME_REPETITION_FRACTION))`` pages out of
       ``N`` total is treated as repeated chrome (e.g. the GPO bill
       footer ``•HR 8752 RH``) and dropped from every page where it
       occurs. The minimum-2 floor prevents a single-page document from
       misclassifying its only chrome line.

    Body-band lines (between the two bands) are always preserved.
    """
    if not pages_lines:
        return pages_lines

    repetition: Counter[tuple[str, str]] = Counter()
    for page_idx, lines in enumerate(pages_lines):
        height = page_heights[page_idx] if page_idx < len(page_heights) else 0.0
        seen_on_page: set[tuple[str, str]] = set()
        for ln in lines:
            band = _band_for_line(ln, height)
            if band is None:
                continue
            text = " ".join(ln.get("text", "").split()).lower()
            if not text:
                continue
            key = (band, text)
            if key in seen_on_page:
                continue
            repetition[key] += 1
            seen_on_page.add(key)

    threshold = max(2, math.ceil(len(pages_lines) * _CHROME_REPETITION_FRACTION))
    repeating: set[tuple[str, str]] = {k for k, c in repetition.items() if c >= threshold}

    out: list[list[Line]] = []
    for page_idx, lines in enumerate(pages_lines):
        height = page_heights[page_idx] if page_idx < len(page_heights) else 0.0
        kept: list[Line] = []
        for ln in lines:
            band = _band_for_line(ln, height)
            if band is not None:
                if _PAGE_NUMBER_ONLY_RE.match(ln.get("text", "")):
                    continue
                text = " ".join(ln.get("text", "").split()).lower()
                if (band, text) in repeating:
                    continue
            kept.append(ln)
        out.append(kept)
    return out


def _line_to_style_hints(line: Line, page_width: float = 612.0) -> cls.StyleHints:
    """Build :class:`classifier.StyleHints` from a Line dict.

    ``indent_level`` is computed from ``x0`` past the body column floor
    (90.0). ``centered`` checks that the line's center sits within 6%
    of the page-width center.
    """
    chars = line.get("chars", []) or []
    text = line.get("text", "")
    x0 = float(line.get("x0", 0.0))
    x1 = float(line.get("x1", x0))
    indent = max(0, int((x0 - 90.0) // 18))
    x_center = (x0 + x1) / 2
    centered = abs(x_center - page_width / 2) < page_width * 0.06
    return cls.StyleHints(
        centered=centered,
        all_caps=cls.is_all_caps(text),
        indent_level=indent,
        font_size=float(chars[0].get("size", 0.0)) if chars else None,
        has_trailing_amount=cls.has_trailing_amount(text),
    )


def _flush_body_to_element(element: ET.Element, body_text: str) -> None:
    """Append ``body_text`` to ``element``'s ``<text>`` child, creating
    the child if absent."""
    if not body_text or element is None:
        return
    text_el = element.find("text")
    if text_el is None:
        text_el = ET.SubElement(element, "text")
        text_el.text = body_text
    else:
        existing = text_el.text or ""
        text_el.text = (existing + " " + body_text).strip() if existing else body_text


def _build_shallow_root(
    classified: list[tuple[cls.Tag, str]],
    *,
    congress: int,
    bill_type: str,
    bill_number: int,
) -> ET.Element:
    """Drive a 2-state machine over classified lines into a shallow
    ElementTree. The walker turns each leaf into a 2-level ``match_path``:

    - SEC. lines pair under the current TITLE (the title_wrapper).
    - APPRO_INTERMEDIATE / APPRO_SMALL lines pair under the current
      APPRO_MAJOR (the major_wrapper). The agency level is the only one
      that disambiguates the heading-collision class (multiple agencies
      have an "Operations and Support" sub-heading).

    Orphan handling:
    - SEC. with no TITLE seen yet: emit directly under ``<legis-body>``.
      The walker's flat-section fallback path handles single-component
      ``match_path`` keys.
    - APPRO_INTERMEDIATE / APPRO_SMALL with no APPRO_MAJOR: synthesize a
      major wrapper using the intermediate's own header so two PDFs of
      the same bill produce identical synthesized labels (deterministic).

    No appropriations-major dollar-paragraph leaf is emitted; in real
    GPO bills the dollar amounts live inside intermediates/smalls. Body
    text encountered between an APPRO_MAJOR header and its first
    intermediate has no leaf to attach to and is dropped (rare in
    practice; lossless for the corpus we have).

    Implementation note: both wrappers are emitted as ``<title>``
    elements directly under ``<legis-body>``. The walker treats every
    ``<title>`` independently, generating a 2-level ``match_path``
    ``(title_header_normalized, leaf_label)`` for each section inside.
    Multiple wrappers under one ``<legis-body>`` is exactly the shape
    ``normalize_bill_from_root`` expects when ``divisions`` is empty
    and ``titles`` is non-empty.
    """
    bill, legis_body = syx.make_root()
    state: dict[str, ET.Element | None] = {
        "title_wrapper": None,  # current TITLE / DIVISION wrapper (for SEC. leaves)
        "major_wrapper": None,  # current APPRO_MAJOR wrapper (for INTER/SMALL leaves)
        "leaf": None,  # most recent leaf (where body accumulates)
    }
    counters: Counter[str] = Counter()
    body_buffer: list[str] = []

    def make_id(tag: str, key_parts: list[str]) -> str:
        counters[tag] += 1
        return syx.synth_id(
            congress=congress,
            bill_type=bill_type,
            bill_number=bill_number,
            tag=tag,
            match_path_parts=key_parts,
            ordinal=counters[tag],
        )

    def flush_body() -> None:
        if not body_buffer:
            return
        text = _join_body_lines(body_buffer)
        body_buffer.clear()
        if state["leaf"] is not None and text:
            _flush_body_to_element(state["leaf"], text)

    def open_title_wrapper(header: str) -> ET.Element:
        wrapper = syx.make_title(
            legis_body,
            header=header,
            element_id=make_id("title", [f"title:{header[:40]}"]),
        )
        state["title_wrapper"] = wrapper
        # New title closes any open major (agencies are title-scoped).
        state["major_wrapper"] = None
        state["leaf"] = None
        return wrapper

    def open_major_wrapper(header: str) -> ET.Element:
        wrapper = syx.make_title(
            legis_body,
            header=header,
            element_id=make_id("title", [f"major:{header[:40]}"]),
        )
        state["major_wrapper"] = wrapper
        state["leaf"] = None
        return wrapper

    for tag, text in classified:
        if tag is cls.Tag.TITLE:
            flush_body()
            parsed = cls.parse_title(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            _enum, header = parsed
            open_title_wrapper(header)
        elif tag is cls.Tag.DIVISION:
            flush_body()
            parsed = cls.parse_division(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            enum, header = parsed
            # Treat divisions like titles in the shallow model -- they're
            # just another wrapper class. Prefix the header so omnibus bills
            # with both DIVISION A's TITLE I and DIVISION B's TITLE I don't
            # collide on the wrapper key.
            open_title_wrapper(f"DIVISION {enum} — {header}")
        elif tag is cls.Tag.APPRO_MAJOR:
            flush_body()
            header = text.strip()
            wrapper = open_major_wrapper(header)
            # Emit a leaf for the major's own body (the dollar paragraph
            # that immediately follows the agency heading -- e.g.
            # "For necessary expenses of [agency], $X..."). Use
            # ``<appropriations-intermediate>`` so the walker produces a
            # 2-level ``match_path`` ``(major_header, major_header)``.
            # The duplication is cosmetic; it pairs cleanly across
            # versions because both PDFs produce the same self-pair.
            # If an actual ``<appropriations-intermediate>`` follows, its
            # body flows into a new leaf as expected.
            leaf = syx.make_appro_intermediate(
                wrapper,
                header=header,
                body_text="",
                element_id=make_id("appropriations-intermediate", [f"major-leaf:{header[:40]}"]),
            )
            state["leaf"] = leaf
        elif tag is cls.Tag.APPRO_INTERMEDIATE:
            flush_body()
            header = text.strip()
            wrapper = state["major_wrapper"] if state["major_wrapper"] is not None else open_major_wrapper(header)
            # Use ``<appropriations-intermediate>`` (not ``<section>``) so the
            # walker's ``_process_appro_element`` puts the leaf header into
            # match_path. Plain ``<section>`` only uses its ``<enum>`` for
            # the leaf component, which we don't have here.
            leaf = syx.make_appro_intermediate(
                wrapper,
                header=header,
                body_text="",
                element_id=make_id("appropriations-intermediate", [f"intermediate:{header[:40]}"]),
            )
            state["leaf"] = leaf
        elif tag is cls.Tag.APPRO_SMALL:
            flush_body()
            parsed = cls.parse_run_in_header(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            header, run_in_body = parsed
            wrapper = state["major_wrapper"] if state["major_wrapper"] is not None else open_major_wrapper(header)
            leaf = syx.make_appro_small(
                wrapper,
                header=header,
                body_text=run_in_body,
                element_id=make_id("appropriations-small", [f"small:{header[:40]}"]),
            )
            state["leaf"] = leaf
        elif tag is cls.Tag.SECTION:
            flush_body()
            parsed = cls.parse_section(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            enum, header = parsed
            parent = state["title_wrapper"] if state["title_wrapper"] is not None else legis_body
            leaf = syx.make_section(
                parent,
                enum=enum,
                header=header,
                body_text="",
                element_id=make_id("section", [f"sec:{enum}"]),
            )
            state["leaf"] = leaf
        else:  # BODY
            body_buffer.append(text)

    flush_body()
    return bill


def parse_pdf(pdf_path: Path) -> BillTree:
    """Parse a PDF bill into a ``BillTree``.

    Pipeline (each step from a prior B-commit):

    - B0: extract chars per page, sort deterministically.
    - B1: group chars into lines with font-size-aware tolerance and
      reattach split-baseline small-caps.
    - B2: strip glued line-number prefixes via the gap discriminator.
    - B6: strip cross-page chrome (footers, page numbers, repeated
      watermark fragments).
    - Concatenate per-page line lists.
    - B3: split off cover-page preamble at the enacting clause (or
      structural fallback).
    - B4: join multi-line TITLE / DIVISION headings into the
      ``TITLE I -- NAME`` form the classifier recognizes.
    - Classify each line into a ``Tag``.
    - B7: drive the state machine to build a synthetic ElementTree.
    - Hand to ``bill_tree.normalize_bill_from_root``.
    """
    pages_chars, heights = _extract_pages(pdf_path)
    congress, bill_type, bill_number, version = _metadata_from_path(pdf_path)

    pages_lines = []
    for chars in pages_chars:
        lines = _strip_line_numbers(_reattach_small_caps(_group_into_lines(chars)))
        pages_lines.append(lines)

    pages_lines = _strip_page_chrome(pages_lines, heights)

    all_lines: list[Line] = [ln for page in pages_lines for ln in page]

    _, body_lines = _split_preamble_and_body(all_lines)
    body_lines = _join_multi_line_titles(body_lines)

    classified: list[tuple[cls.Tag, str]] = []
    for ln in body_lines:
        hints = _line_to_style_hints(ln)
        tag = cls.classify(ln.get("text", ""), hints)
        classified.append((tag, ln.get("text", "")))

    root = _build_shallow_root(
        classified,
        congress=congress,
        bill_type=bill_type,
        bill_number=bill_number,
    )
    return normalize_bill_from_root(
        root,
        congress=congress,
        bill_type=bill_type,
        bill_number=bill_number,
        version=version,
    )
