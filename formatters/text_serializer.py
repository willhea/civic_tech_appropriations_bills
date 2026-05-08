"""Serialize a normalized BillTree into readable plaintext.

Used to populate the canonical diff JSON's optional `full_text` field so
renderers can run a Word-style tracked-changes diff over the whole
document, not just per-change fragments.

The format is intentionally simple: emit each new display_path segment as
its own heading line on first appearance, then emit the node's body text.
Sibling nodes under a shared parent path share that parent's heading.
"""

from __future__ import annotations

from bill_tree import BillTree


def serialize_tree(tree: BillTree) -> str:
    """Walk the flat node list and emit hierarchical plaintext.

    Heading emission rule: when transitioning from one node to the next,
    diff the display_path tuples. Any new trailing segments are emitted
    as headings (one per line), each separated by a blank line. Body text
    follows on its own line(s), then a trailing blank line before the next
    node.
    """
    out: list[str] = []
    prev_path: tuple[str, ...] = ()
    for node in tree.nodes:
        new_path = tuple(node.display_path)
        # Find the longest common prefix between previous and new path.
        common = 0
        while common < len(prev_path) and common < len(new_path) and prev_path[common] == new_path[common]:
            common += 1
        # Emit any newly entered path segments as headings.
        for seg in new_path[common:]:
            if out and out[-1] != "":
                out.append("")
            out.append(seg)
        # Some nodes carry a header_text that isn't already the last path
        # segment (e.g., enacting clause has empty path but a header).
        if not new_path and node.header_text:
            out.append(node.header_text)
        if node.body_text:
            if out and out[-1] != "":
                out.append("")
            out.append(node.body_text)
            out.append("")
        prev_path = new_path
    # Trim trailing blank lines.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)
