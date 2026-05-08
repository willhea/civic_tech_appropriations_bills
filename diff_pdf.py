"""Block-level diff for PDF bill versions, parallel to diff_bill.py for XML.

A bill is grouped into anchor-delimited blocks (TITLE / SEC. / account heading)
on each side, then aligned section-by-section. Lines before the first anchor
form a preamble block. The block is the natural unit of comparison — it mirrors
how `diff_bill.match_nodes` operates on BillTree nodes for XML and avoids the
SequenceMatcher line-level fragmentation that produced over-counted hunks and
missed added/moved sections.

Within matched blocks, the renderer applies word-level diff against the joined
block text. The classifier produces:

- `added` — block present only in v2
- `removed` — block present only in v1
- `moved` — block bodies similar but anchors differ (renumbered SEC.)
- `modified` — paired blocks with different bodies

Reuses amount extraction (`extract_amounts`, `match_amounts`) and text
similarity (`_text_similarity`) from diff_bill.py.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from diff_bill import _text_similarity, match_amounts
from parsers.pdf_anchors import Anchor, extract_anchors
from parsers.pdf_text import Page

ChangeType = Literal["added", "removed", "modified", "moved"]
PageLineRange = tuple[int, int, int, int]  # (start_page, start_line, end_page, end_line)

_AMENDMENT_RE_DETAIL = re.compile(r"\((increased|reduced|decreased) by\s+\$([\d,]+)\)")

# Body similarity needed to call a block-pair "moved" rather than "modified",
# and to reconcile a removed+added pair as moved. Matches diff_bill's threshold.
_MOVE_SIMILARITY_THRESHOLD = 0.6

# Below this similarity, two blocks paired by alignment aren't really a
# modified pair — they're an unrelated removal + addition that happen to
# share an anchor (e.g. v1 SEC. 413 = H-2A waiver, v2 SEC. 413 = Asylum
# Fee renumbered from SEC. 414). Split them so reconcile_moves can pair
# v1 SEC. 414 with v2 SEC. 413 by body similarity. Matches diff_bill's
# _SIMILARITY_THRESHOLD.
_PAIR_BODY_THRESHOLD = 0.4


@dataclass(frozen=True)
class PdfHunk:
    change_type: ChangeType
    v1_anchor: Anchor | None
    v2_anchor: Anchor | None
    v1_range: PageLineRange | None
    v2_range: PageLineRange | None
    v1_text: str
    v2_text: str
    amount_pairs: tuple[tuple[int | None, int | None], ...] = ()
    has_amendment_annotations: bool = False  # mirrors FinancialChange field for XML parity


@dataclass(frozen=True)
class PdfDiff:
    hunks: tuple[PdfHunk, ...]
    v1_anchors: tuple[Anchor, ...] = ()
    v2_anchors: tuple[Anchor, ...] = ()

    @property
    def summary(self) -> dict[str, int]:
        return dict(Counter(h.change_type for h in self.hunks))


# ---- Internal helpers --------------------------------------------------------


@dataclass(frozen=True)
class _IndexedLine:
    text: str
    page_number: int
    line_number: int | None  # None when source PDF didn't number this line


@dataclass(frozen=True)
class _Block:
    """An anchor-delimited group of lines.

    `anchor` is None only for the preamble (lines before the first anchor on
    either side, e.g. cover page, enacting clause). The `indexed_lines` start
    with the anchor's own line and run until the next anchor.
    """

    anchor: Anchor | None
    indexed_lines: tuple[_IndexedLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.indexed_lines)

    @property
    def page_range(self) -> PageLineRange | None:
        if not self.indexed_lines:
            return None
        first, last = self.indexed_lines[0], self.indexed_lines[-1]
        return (
            first.page_number,
            first.line_number if first.line_number is not None else -1,
            last.page_number,
            last.line_number if last.line_number is not None else -1,
        )


def _flatten(pages: list[Page]) -> list[_IndexedLine]:
    """Flatten pages into a single ordered list of (text, page, line) records."""
    flat: list[_IndexedLine] = []
    for page in pages:
        for line in page.lines:
            flat.append(_IndexedLine(line.text, page.page_number, line.line_number))
    return flat


def _group_into_blocks(indexed_lines: list[_IndexedLine], anchors: list[Anchor]) -> list[_Block]:
    """Group lines into anchor-delimited blocks.

    Lines preceding the first anchor become a preamble block (anchor=None).
    Each subsequent anchor starts a new block that runs until the next anchor.
    """
    if not indexed_lines:
        return []

    # Build a (page, line) → first-occurrence-index map so anchor lookup is O(1).
    # `line.index(...)` would be O(n) per anchor, making this loop O(anchors × lines).
    line_index: dict[tuple[int, int | None], int] = {}
    for i, ln in enumerate(indexed_lines):
        key = (ln.page_number, ln.line_number)
        if key not in line_index:
            line_index[key] = i

    anchor_positions: list[int] = []
    for a in anchors:
        pos = line_index.get((a.page_number, a.line_number))
        if pos is None:
            # Anchor's line was rejoined into a previous line during cleanup;
            # skip — its text is already part of an earlier line and will end
            # up in the previous block.
            continue
        anchor_positions.append(pos)

    blocks: list[_Block] = []
    if not anchor_positions:
        # No anchors at all — entire document is preamble.
        return [_Block(None, tuple(indexed_lines))]

    if anchor_positions[0] > 0:
        blocks.append(_Block(None, tuple(indexed_lines[: anchor_positions[0]])))

    for j, pos in enumerate(anchor_positions):
        end = anchor_positions[j + 1] if j + 1 < len(anchor_positions) else len(indexed_lines)
        blocks.append(_Block(anchors[j], tuple(indexed_lines[pos:end])))

    return blocks


def _block_key(block: _Block) -> str:
    """Alignment key for SequenceMatcher.

    Combines anchor text (e.g. "SEC. 101", "OPERATIONS AND SUPPORT") with the
    first ~80 chars of the block's body to disambiguate non-unique account
    headings while staying stable to amendment annotations appearing later
    in the body.
    """
    anchor_text = block.anchor.text if block.anchor else "(preamble)"
    body_preview = block.text[:80].strip()
    return f"{anchor_text}::{body_preview}"


def _amount_pairs(v1_text: str, v2_text: str) -> tuple[tuple[int | None, int | None], ...]:
    """All amount pairs from match_amounts as a tuple, including unchanged pairs.

    Unchanged pairs (e.g. `$281,358,000 → $281,358,000` when only floor
    amendment annotations were added) are preserved here so the renderer can
    show them in the callout — matches the XML pipeline's
    `_financial_callout`, which renders every paired amount including `(+$0)`
    rows. The Financial Summary table at the top still filters to truly-changed
    pairs via `_has_real_amount_change` in the renderer.
    """
    return tuple(match_amounts(v1_text, v2_text))


def _has_amendment_annotations(v1_text: str, v2_text: str) -> bool:
    """True if either side carries a floor amendment annotation.

    Mirrors `FinancialChange.has_amendment_annotations` in diff_bill.py.
    """
    return bool(_AMENDMENT_RE_DETAIL.search(v1_text) or _AMENDMENT_RE_DETAIL.search(v2_text))


def _hunk_for_paired_blocks(v1_block: _Block, v2_block: _Block, similarity: float | None = None) -> PdfHunk:
    """Emit a hunk for two blocks paired by alignment.

    Classifies as `moved` when anchors differ but bodies are highly similar
    (renumbered SEC.), else `modified`. Caller has already confirmed v1 and v2
    block texts differ — this routine doesn't filter equal blocks.

    `similarity`, if provided, is the precomputed `_text_similarity` between
    v1 and v2 text. Caller can pass it to avoid a second computation when it
    already had to compute one (e.g. to decide split-vs-pair upstream).
    """
    v1_text = v1_block.text
    v2_text = v2_block.text
    v1_anchor = v1_block.anchor
    v2_anchor = v2_block.anchor
    if v1_anchor and v2_anchor and v1_anchor.text != v2_anchor.text:
        if similarity is None:
            similarity = _text_similarity(v1_text, v2_text)
        change_type: ChangeType = "moved" if similarity >= _MOVE_SIMILARITY_THRESHOLD else "modified"
    else:
        change_type = "modified"
    return PdfHunk(
        change_type=change_type,
        v1_anchor=v1_anchor,
        v2_anchor=v2_anchor,
        v1_range=v1_block.page_range,
        v2_range=v2_block.page_range,
        v1_text=v1_text,
        v2_text=v2_text,
        amount_pairs=_amount_pairs(v1_text, v2_text),
        has_amendment_annotations=_has_amendment_annotations(v1_text, v2_text),
    )


def _hunk_for_added(v2_block: _Block) -> PdfHunk:
    return PdfHunk(
        change_type="added",
        v1_anchor=None,
        v2_anchor=v2_block.anchor,
        v1_range=None,
        v2_range=v2_block.page_range,
        v1_text="",
        v2_text=v2_block.text,
        amount_pairs=(),
        has_amendment_annotations=_has_amendment_annotations("", v2_block.text),
    )


def _hunk_for_removed(v1_block: _Block) -> PdfHunk:
    return PdfHunk(
        change_type="removed",
        v1_anchor=v1_block.anchor,
        v2_anchor=None,
        v1_range=v1_block.page_range,
        v2_range=None,
        v1_text=v1_block.text,
        v2_text="",
        amount_pairs=(),
        has_amendment_annotations=_has_amendment_annotations(v1_block.text, ""),
    )


def _reconcile_moves(hunks: list[PdfHunk], threshold: float = _MOVE_SIMILARITY_THRESHOLD) -> list[PdfHunk]:
    """Pair `removed`+`added` hunks whose bodies are highly similar into `moved` hunks.

    Catches renumbered sections (e.g. SEC. 414 in v1 → SEC. 413 in v2) when block
    keys diverge enough that SequenceMatcher emitted them as separate insert
    and delete rather than aligning them. Mirrors `diff_bill.reconcile_moves`.
    """
    removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
    added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]
    if not removed_idx or not added_idx:
        return hunks

    candidates: list[tuple[float, int, int]] = []
    for ri in removed_idx:
        for ai in added_idx:
            sim = _text_similarity(hunks[ri].v1_text, hunks[ai].v2_text)
            if sim >= threshold:
                candidates.append((sim, ri, ai))
    if not candidates:
        return hunks

    candidates.sort(reverse=True)
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    moved_pairs: list[tuple[int, int]] = []
    for _, ri, ai in candidates:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        moved_pairs.append((ri, ai))

    consumed = claimed_r | claimed_a
    moved_lookup = {ri: ai for ri, ai in moved_pairs}
    result: list[PdfHunk] = []
    for i, h in enumerate(hunks):
        if i in moved_lookup:
            removed = h
            added = hunks[moved_lookup[i]]
            result.append(
                PdfHunk(
                    change_type="moved",
                    v1_anchor=removed.v1_anchor,
                    v2_anchor=added.v2_anchor,
                    v1_range=removed.v1_range,
                    v2_range=added.v2_range,
                    v1_text=removed.v1_text,
                    v2_text=added.v2_text,
                    amount_pairs=_amount_pairs(removed.v1_text, added.v2_text),
                    has_amendment_annotations=_has_amendment_annotations(removed.v1_text, added.v2_text),
                )
            )
        elif i in consumed:
            continue
        else:
            result.append(h)
    return result


# ---- Public entry point ------------------------------------------------------


def diff_pdfs(v1_pages: list[Page], v2_pages: list[Page]) -> PdfDiff:
    """Block-level diff of two extracted PDF page sequences."""
    v1_indexed = _flatten(v1_pages)
    v2_indexed = _flatten(v2_pages)
    v1_anchors = extract_anchors(v1_pages)
    v2_anchors = extract_anchors(v2_pages)

    v1_blocks = _group_into_blocks(v1_indexed, v1_anchors)
    v2_blocks = _group_into_blocks(v2_indexed, v2_anchors)

    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks],
        b=[_block_key(b) for b in v2_blocks],
        autojunk=False,
    )

    def _emit_pair(v1_b: _Block, v2_b: _Block, sink: list[PdfHunk]) -> None:
        """Emit a paired-block hunk OR split into removed+added if bodies disagree."""
        if v1_b.text == v2_b.text:
            return
        sim = _text_similarity(v1_b.text, v2_b.text)
        if sim < _PAIR_BODY_THRESHOLD:
            sink.append(_hunk_for_removed(v1_b))
            sink.append(_hunk_for_added(v2_b))
        else:
            sink.append(_hunk_for_paired_blocks(v1_b, v2_b, similarity=sim))

    hunks: list[PdfHunk] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            # Block keys match. Bodies might still differ (e.g. amendment
            # annotations appearing past the 80-char preview).
            for v1_b, v2_b in zip(v1_blocks[i1:i2], v2_blocks[j1:j2]):
                _emit_pair(v1_b, v2_b, hunks)
        elif op == "delete":
            for v1_b in v1_blocks[i1:i2]:
                hunks.append(_hunk_for_removed(v1_b))
        elif op == "insert":
            for v2_b in v2_blocks[j1:j2]:
                hunks.append(_hunk_for_added(v2_b))
        else:  # replace
            v1_slice = v1_blocks[i1:i2]
            v2_slice = v2_blocks[j1:j2]
            # Pair positionally; surplus on either side becomes added/removed.
            for k in range(max(len(v1_slice), len(v2_slice))):
                v1_b = v1_slice[k] if k < len(v1_slice) else None
                v2_b = v2_slice[k] if k < len(v2_slice) else None
                if v1_b is not None and v2_b is not None:
                    _emit_pair(v1_b, v2_b, hunks)
                elif v1_b is not None:
                    hunks.append(_hunk_for_removed(v1_b))
                else:
                    assert v2_b is not None
                    hunks.append(_hunk_for_added(v2_b))

    return PdfDiff(
        hunks=tuple(_reconcile_moves(hunks)),
        v1_anchors=tuple(v1_anchors),
        v2_anchors=tuple(v2_anchors),
    )
