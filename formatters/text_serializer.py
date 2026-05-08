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
        # For section nodes, the trailing display_path segment is a lowercased
        # copy of section_number ("sec. 101"). Drop it from the heading run so
        # we can emit a bill-style "SEC. 101." run-in heading on the body line.
        heading_path = new_path[:-1] if node.section_number and new_path else new_path
        # Find the longest common prefix between previous and new path.
        common = 0
        while common < len(prev_path) and common < len(heading_path) and prev_path[common] == heading_path[common]:
            common += 1
        # Emit any newly entered path segments as headings.
        for seg in heading_path[common:]:
            if out and out[-1] != "":
                out.append("")
            out.append(seg)
        # Some nodes carry a header_text that isn't already the last path
        # segment (e.g., enacting clause has empty path but a header).
        if not new_path and node.header_text:
            out.append(node.header_text)
        # Body: section nodes get "SEC. NN." prefixed as a run-in heading;
        # everything else just emits body_text on its own.
        if node.body_text:
            if out and out[-1] != "":
                out.append("")
            if node.section_number:
                out.append(f"{node.section_number.upper()}.  {node.body_text}")
            else:
                out.append(node.body_text)
            out.append("")
        prev_path = heading_path
    # Trim trailing blank lines.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)
