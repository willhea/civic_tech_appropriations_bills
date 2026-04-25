"""PDF -> BillTree parser.

The pipeline (see ``plans/so-we-talked-to-drifting-sundae.md``):

1. Extract per-character data from each page via pdfplumber.
2. Strip watermark characters (rotation + pale-fill).
3. Group surviving chars into lines.
4. Strip page-level noise (line numbers, page numbers, running headers,
   repeated centered overlays).
5. Join wrapped headers.
6. Classify each line and drive a state machine that builds a
   Congress.gov-shaped synthetic ElementTree.
7. Hand the tree to ``normalize_bill_from_root``.

The intermediate stages are pure functions over plain dicts so they can
be exercised without a real PDF in tests.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from bill_tree import BillTree, normalize_bill_from_root

from . import classifier as cls
from . import synthetic_xml as syx

Char = dict[str, Any]
Line = dict[str, Any]
Page = list[Line]


# --- Tunables -------------------------------------------------------------

ROTATION_TOLERANCE_DEG = 5.0
PALE_LUMINANCE_THRESHOLD = 0.7
LINE_GROUP_TOLERANCE = 2.0  # px for grouping chars into a line by `top`
BODY_COLUMN_X_MIN = 90.0  # GPO line-number margin ends near here
PAGE_HEADER_BAND = 50.0  # top N px treated as running-header band
PAGE_FOOTER_BAND = 60.0  # bottom N px treated as page-number band
OVERLAY_REPETITION_RATIO = 0.5  # > this fraction of pages -> overlay
OVERLAY_MAX_TOKENS = 3
OVERLAY_POSITION_BUCKET = 20.0  # px quantization for repetition match


# --- Watermark stripping (char-level) -------------------------------------


def _char_rotation_deg(matrix: Sequence[float] | None) -> float:
    """Return the rotation of a char in degrees, or 0.0 if unknown."""
    if not matrix or len(matrix) < 4:
        return 0.0
    a, b = matrix[0], matrix[1]
    return math.degrees(math.atan2(b, a))


def _color_luminance(color: Any) -> float | None:
    """Resolve a pdfplumber ``non_stroking_color`` value to luminance.

    Returns ``None`` when the color can't be interpreted (e.g., named
    colorspace) so callers fall back to keeping the char.
    """
    if color is None:
        return 0.0  # default to black
    if isinstance(color, (int, float)):
        return float(color)
    if isinstance(color, (list, tuple)):
        if len(color) == 1:
            return float(color[0])
        if len(color) == 3:
            r, g, b = (float(c) for c in color)
            return 0.299 * r + 0.587 * g + 0.114 * b
        if len(color) == 4:
            c, m, y, k = (float(v) for v in color)
            rough = 1.0 - min(1.0, k + 0.5 * (c + m + y))
            return max(0.0, rough)
    return None


def _is_watermark_char(ch: Char) -> bool:
    """Return True if ``ch`` looks like a watermark glyph.

    Combines the rotation and pale-fill filters from the plan.
    """
    rotation = _char_rotation_deg(ch.get("matrix"))
    if abs(rotation) > ROTATION_TOLERANCE_DEG:
        return True
    luminance = _color_luminance(ch.get("non_stroking_color"))
    if luminance is not None and luminance > PALE_LUMINANCE_THRESHOLD:
        return True
    return False


def strip_watermark_chars(chars: Iterable[Char]) -> list[Char]:
    """Return ``chars`` with watermark glyphs removed."""
    return [ch for ch in chars if not _is_watermark_char(ch)]


# --- Line grouping --------------------------------------------------------


def group_lines(chars: Iterable[Char]) -> list[Line]:
    """Group chars into lines by ``top`` and concatenate text in x-order.

    Returns one dict per line with keys:
    ``text``, ``top``, ``x0``, ``x1``, ``chars``.
    """
    by_top: list[tuple[float, list[Char]]] = []
    for ch in sorted(chars, key=lambda c: (c.get("top", 0.0), c.get("x0", 0.0))):
        top = float(ch.get("top", 0.0))
        placed = False
        for i, (bucket_top, bucket_chars) in enumerate(by_top):
            if abs(bucket_top - top) <= LINE_GROUP_TOLERANCE:
                bucket_chars.append(ch)
                # Update the bucket's nominal top to the running mean so
                # tolerance drift doesn't accumulate.
                new_top = (bucket_top * len(bucket_chars) + top) / (len(bucket_chars) + 1)
                by_top[i] = (new_top, bucket_chars)
                placed = True
                break
        if not placed:
            by_top.append((top, [ch]))

    lines: list[Line] = []
    for top, chars_in_line in sorted(by_top, key=lambda b: b[0]):
        chars_sorted = sorted(chars_in_line, key=lambda c: c.get("x0", 0.0))
        text = "".join(c.get("text", "") for c in chars_sorted)
        if not chars_sorted:
            continue
        lines.append(
            {
                "text": text,
                "top": top,
                "x0": chars_sorted[0].get("x0", 0.0),
                "x1": chars_sorted[-1].get("x1", chars_sorted[-1].get("x0", 0.0)),
                "chars": chars_sorted,
            }
        )
    return lines


# --- Page-level noise stripping ------------------------------------------


_LINE_NUMBER_RE = re.compile(r"^\d{1,3}$")


def _strip_line_numbers(lines: list[Line]) -> list[Line]:
    """Drop lines whose tokens fall in the GPO line-number margin."""
    out: list[Line] = []
    for ln in lines:
        text = ln["text"].strip()
        if ln["x0"] < BODY_COLUMN_X_MIN and _LINE_NUMBER_RE.match(text):
            continue
        # Also strip leading line-number tokens from a line that has them
        # plus body text on the same y (some PDFs typeset that way).
        chars = [c for c in ln["chars"] if c.get("x0", 0.0) >= BODY_COLUMN_X_MIN]
        if not chars:
            continue
        if len(chars) != len(ln["chars"]):
            ln = dict(ln)
            ln["chars"] = chars
            ln["text"] = "".join(c.get("text", "") for c in chars)
            ln["x0"] = chars[0].get("x0", 0.0)
        out.append(ln)
    return out


def _strip_page_numbers(lines: list[Line], page_height: float) -> list[Line]:
    """Drop short numeric-only lines near the page bottom."""
    threshold = page_height - PAGE_FOOTER_BAND
    return [ln for ln in lines if not (ln["top"] >= threshold and _LINE_NUMBER_RE.match(ln["text"].strip()))]


def strip_page_noise(lines: list[Line], page_height: float) -> list[Line]:
    """Remove line numbers and page numbers from a single page's lines."""
    lines = _strip_line_numbers(lines)
    lines = _strip_page_numbers(lines, page_height)
    return lines


# --- Cross-page repetition stripping (running headers + overlay) ----------


_KNOWN_HEADER_PREFIXES = ("H. R.", "S.", "Calendar No.")


def _normalized_short(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _strip_running_headers(pages: list[Page]) -> list[Page]:
    """Drop any line in the top header band that recurs across >50% of pages.

    Falls back to a known-prefix list for short bills where the
    repetition rule has too few samples.
    """
    if not pages:
        return pages

    header_lines: Counter[str] = Counter()
    for page in pages:
        seen: set[str] = set()
        for ln in page:
            if ln["top"] > PAGE_HEADER_BAND:
                continue
            key = _normalized_short(ln["text"])
            if key and key not in seen:
                header_lines[key] += 1
                seen.add(key)

    threshold = max(1, math.ceil(len(pages) * OVERLAY_REPETITION_RATIO) + 1) if len(pages) >= 4 else 0
    to_drop_repeated = {key for key, count in header_lines.items() if threshold and count > threshold}

    out: list[Page] = []
    for page in pages:
        kept: Page = []
        for ln in page:
            if ln["top"] <= PAGE_HEADER_BAND:
                key = _normalized_short(ln["text"])
                if key in to_drop_repeated:
                    continue
                if any(ln["text"].strip().startswith(p) for p in _KNOWN_HEADER_PREFIXES):
                    continue
            kept.append(ln)
        out.append(kept)
    return out


def _strip_repeated_overlay(pages: list[Page], page_height: float) -> list[Page]:
    """Drop short centered lines that repeat across most pages (watermark)."""
    if len(pages) < 2:
        return pages

    body_band_top = PAGE_HEADER_BAND
    body_band_bottom = page_height - PAGE_FOOTER_BAND

    # Bucket each candidate line by (text, x_center_bucket, top_bucket).
    counts: Counter[tuple[str, int, int]] = Counter()
    for page in pages:
        seen: set[tuple[str, int, int]] = set()
        for ln in page:
            if not (body_band_top < ln["top"] < body_band_bottom):
                continue
            tokens = ln["text"].split()
            if not tokens or len(tokens) > OVERLAY_MAX_TOKENS:
                continue
            key = _overlay_key(ln)
            if key in seen:
                continue
            counts[key] += 1
            seen.add(key)

    threshold = math.ceil(len(pages) * OVERLAY_REPETITION_RATIO)
    drop = {key for key, count in counts.items() if count > threshold}

    out: list[Page] = []
    for page in pages:
        kept: Page = []
        for ln in page:
            if _overlay_key(ln) in drop:
                continue
            kept.append(ln)
        out.append(kept)
    return out


def _overlay_key(line: Line) -> tuple[str, int, int]:
    text_key = _normalized_short(line["text"])
    x_center = (float(line["x0"]) + float(line["x1"])) / 2
    return (
        text_key,
        int(x_center // OVERLAY_POSITION_BUCKET),
        int(float(line["top"]) // OVERLAY_POSITION_BUCKET),
    )


# --- Wrapped-header join --------------------------------------------------


_TERMINATING_CHARS = ".!?:;"


def join_wrapped_headers(lines: list[Line]) -> list[Line]:
    """Merge consecutive heading-like lines that share an indent column.

    A heading wraps onto a continuation line when:
    - the previous line is short (<= 80 chars) and starts uppercase,
    - the current line starts at roughly the same x0,
    - the previous line doesn't terminate with sentence punctuation.
    """
    out: list[Line] = []
    for ln in lines:
        if not out:
            out.append(ln)
            continue
        prev = out[-1]
        prev_text = prev["text"].rstrip()
        if (
            prev_text
            and prev_text[-1] not in _TERMINATING_CHARS
            and len(prev_text) <= 80
            and prev_text[:1].isupper()
            and abs(float(prev["x0"]) - float(ln["x0"])) < 4.0
            and float(ln["top"]) - float(prev["top"]) < 24.0
            and ln["text"].strip()[:1].isupper()
        ):
            joined = dict(prev)
            joined["text"] = f"{prev_text} {ln['text'].strip()}"
            joined["x1"] = max(float(prev["x1"]), float(ln["x1"]))
            joined["chars"] = list(prev["chars"]) + list(ln["chars"])
            out[-1] = joined
        else:
            out.append(ln)
    return out


# --- Style hint extraction ------------------------------------------------


def _line_style_hints(line: Line, page_width: float) -> cls.StyleHints:
    chars = line.get("chars", [])
    fonts = [c.get("fontname", "") for c in chars]
    bold = any("Bold" in f or "Black" in f for f in fonts)
    italic = any("Italic" in f or "Oblique" in f for f in fonts)
    indent_level = max(0, int((float(line["x0"]) - BODY_COLUMN_X_MIN) // 18))
    line_center = (float(line["x0"]) + float(line["x1"])) / 2
    centered = abs(line_center - page_width / 2) < page_width * 0.06
    text = line["text"].strip()
    return cls.StyleHints(
        centered=centered,
        all_caps=cls.is_all_caps(text),
        bold=bold,
        italic=italic,
        indent_level=indent_level,
        font_size=float(chars[0].get("size", 0.0)) if chars else None,
        has_trailing_amount=cls.has_trailing_amount(text),
    )


# --- State machine: classified lines -> synthetic ElementTree -------------


def _new_id_factory(*, congress: int, bill_type: str, bill_number: int):
    counters: Counter[str] = Counter()

    def make(tag: str, match_path_parts: Iterable[str]) -> str:
        counters[tag] += 1
        return syx.synth_id(
            congress=congress,
            bill_type=bill_type,
            bill_number=bill_number,
            tag=tag,
            match_path_parts=match_path_parts,
            ordinal=counters[tag],
        )

    return make


def lines_to_synthetic_root(
    classified: list[tuple[cls.Tag, str, cls.StyleHints]],
    *,
    congress: int,
    bill_type: str,
    bill_number: int,
) -> ET.Element:
    """Drive a state machine over classified lines and return a ``<bill>``.

    The state tracks the deepest open content container so body lines
    flow into the right ``<text>`` node, mimicking the XML structure the
    walkers in ``bill_tree.py`` already understand.
    """
    bill, legis_body = syx.make_root()
    make_id = _new_id_factory(congress=congress, bill_type=bill_type, bill_number=bill_number)

    state: dict[str, ET.Element | None] = {
        "division": None,
        "title": None,
        "major": None,
        "intermediate": None,
        "leaf": None,  # the deepest content container (section / appro-*)
    }
    body_buffer: list[str] = []
    path_breadcrumbs: list[str] = []

    def flush_body() -> None:
        if not body_buffer:
            return
        text = " ".join(body_buffer).strip()
        body_buffer.clear()
        if not text:
            return
        leaf = state["leaf"]
        if leaf is None:
            return
        # Append to existing <text> if present, else add one.
        existing = leaf.find("text")
        if existing is None:
            text_el = ET.SubElement(leaf, "text")
            text_el.text = text
        else:
            existing.text = f"{existing.text or ''} {text}".strip()

    def parent_for_title() -> ET.Element:
        return state["division"] if state["division"] is not None else legis_body

    def parent_for_appro() -> ET.Element:
        return state["title"] if state["title"] is not None else parent_for_title()

    for tag, text, hints in classified:
        if tag is cls.Tag.DIVISION:
            flush_body()
            parsed = cls.parse_division(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            enum, header = parsed
            path_breadcrumbs = [f"div:{enum}"]
            state["division"] = syx.make_division(
                legis_body,
                enum=enum,
                header=header,
                element_id=make_id("division", path_breadcrumbs),
            )
            state["title"] = state["major"] = state["intermediate"] = state["leaf"] = None
        elif tag is cls.Tag.TITLE:
            flush_body()
            parsed = cls.parse_title(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            enum, header = parsed
            path_breadcrumbs = (path_breadcrumbs[:1] if state["division"] is not None else []) + [f"title:{enum}"]
            state["title"] = syx.make_title(
                parent_for_title(),
                enum=enum,
                header=header,
                element_id=make_id("title", path_breadcrumbs),
            )
            state["major"] = state["intermediate"] = state["leaf"] = None
        elif tag is cls.Tag.APPRO_MAJOR:
            flush_body()
            path_breadcrumbs = path_breadcrumbs[: 1 if state["division"] is not None else 0]
            if state["title"] is not None:
                path_breadcrumbs = path_breadcrumbs + [f"title:{_short(text)}"]
            path_breadcrumbs = path_breadcrumbs + [f"major:{_short(text)}"]
            major = syx.make_appro_major(
                parent_for_appro(),
                header=text,
                body_text="",
                element_id=make_id("appropriations-major", path_breadcrumbs),
            )
            state["major"] = state["leaf"] = major
            state["intermediate"] = None
        elif tag is cls.Tag.APPRO_INTERMEDIATE:
            flush_body()
            parent = state["major"] if state["major"] is not None else parent_for_appro()
            breadcrumbs = path_breadcrumbs + [f"intermediate:{_short(text)}"]
            inter = syx.make_appro_intermediate(
                parent,
                header=text,
                body_text="",
                element_id=make_id("appropriations-intermediate", breadcrumbs),
            )
            state["intermediate"] = state["leaf"] = inter
        elif tag is cls.Tag.APPRO_SMALL:
            flush_body()
            parent = (
                state["intermediate"]
                if state["intermediate"] is not None
                else (state["major"] if state["major"] is not None else parent_for_appro())
            )
            run_in = cls.parse_run_in_header(text)
            if run_in is None:
                body_buffer.append(text)
                continue
            header, body_text = run_in
            breadcrumbs = path_breadcrumbs + [f"small:{_short(header)}"]
            small = syx.make_appro_small(
                parent,
                header=header,
                body_text=body_text,
                element_id=make_id("appropriations-small", breadcrumbs),
            )
            state["leaf"] = small
        elif tag is cls.Tag.SECTION:
            flush_body()
            parsed = cls.parse_section(text)
            if parsed is None:
                body_buffer.append(text)
                continue
            enum, header = parsed
            parent = state["title"] if state["title"] is not None else parent_for_title()
            breadcrumbs = path_breadcrumbs + [f"sec:{enum}"]
            section = syx.make_section(
                parent,
                enum=enum,
                header=header,
                body_text="",
                element_id=make_id("section", breadcrumbs),
            )
            state["leaf"] = section
        else:  # BODY
            body_buffer.append(text)

    flush_body()
    return bill


def _short(text: str) -> str:
    return " ".join(text.split())[:48].lower()


# --- Top-level entry points ----------------------------------------------


def _metadata_from_path(pdf_path: Path) -> tuple[int, str, int, str]:
    """Derive (congress, bill_type, bill_number, version) from path layout.

    Expected: ``<corpus>/<congress>-<bill_type>-<bill_number>/<n>_<slug>.pdf``.
    Returns zeros / empty strings for components that don't parse.
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
    stem = pdf_path.stem
    stem_parts = stem.split("_", 1)
    if len(stem_parts) == 2:
        version = stem_parts[1]
    return congress, bill_type, bill_number, version


def _extract_pages(pdf_path: Path) -> tuple[list[list[Char]], list[float]]:
    """Read each page's chars and height via pdfplumber."""
    import pdfplumber  # imported lazily so the dep is optional at import time

    pages: list[list[Char]] = []
    heights: list[float] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(list(page.chars))
            heights.append(float(page.height))
    return pages, heights


def parse_pdf_pages(
    pages: list[list[Char]],
    page_heights: list[float],
    *,
    congress: int,
    bill_type: str,
    bill_number: int,
    version: str,
) -> BillTree:
    """Run the full pipeline over already-extracted page data.

    Exposed separately so tests can hand in synthetic char dicts without
    needing pdfplumber or a real PDF on disk.
    """
    page_lines: list[Page] = []
    for chars, height in zip(pages, page_heights):
        chars = strip_watermark_chars(chars)
        lines = group_lines(chars)
        lines = strip_page_noise(lines, height)
        page_lines.append(lines)

    page_lines = _strip_running_headers(page_lines)
    if page_heights:
        page_lines = _strip_repeated_overlay(page_lines, max(page_heights))

    flat: list[Line] = []
    for page in page_lines:
        flat.extend(page)
    flat = join_wrapped_headers(flat)

    page_width = 612.0  # standard US letter; hints use it for centering.
    classified: list[tuple[cls.Tag, str, cls.StyleHints]] = []
    trace: list[dict[str, Any]] = []
    for ln in flat:
        hints = _line_style_hints(ln, page_width)
        tag = cls.classify(ln["text"], hints)
        classified.append((tag, ln["text"], hints))
        if os.environ.get("BILL_DIFF_TRACE_CLASSIFY") == "1":
            trace.append(
                {
                    "tag": tag.value,
                    "text": ln["text"],
                    "top": ln["top"],
                    "x0": ln["x0"],
                    "centered": hints.centered,
                    "all_caps": hints.all_caps,
                    "indent_level": hints.indent_level,
                }
            )

    if trace:
        import json

        Path("classify_trace.json").write_text(json.dumps(trace, indent=2))

    root = lines_to_synthetic_root(
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


def parse_pdf(pdf_path: Path) -> BillTree:
    """Parse a PDF bill into a normalized BillTree."""
    pages, heights = _extract_pages(pdf_path)
    congress, bill_type, bill_number, version = _metadata_from_path(pdf_path)
    return parse_pdf_pages(
        pages,
        heights,
        congress=congress,
        bill_type=bill_type,
        bill_number=bill_number,
        version=version,
    )
