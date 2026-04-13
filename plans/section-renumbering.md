# Section Renumbering Limitation

## Problem

When sections are inserted or removed between bill versions, existing sections get renumbered. The diff tool matches by section number, so a renumbered section appears as a removal + addition instead of a modification.

Example from HR 8282 (ICC sanctions bill):

| Introduced (v1) | Engrossed (v2) |
|---|---|
| Sec. 1: Short title | Sec. 1: Short title |
| Sec. 2: Sanctions | Sec. 2: Findings (NEW) |
| Sec. 3: Definitions | Sec. 3: Sanctions (was Sec. 2) |
| | Sec. 4: Rescission (NEW) |
| | Sec. 5: Definitions (was Sec. 3) |

The Sanctions section moved from Sec. 2 to Sec. 3, so the tool reports old Sec. 2 as removed and new Sec. 3 as added. The text similarity threshold correctly prevents the false match between old Sec. 2 (sanctions) and new Sec. 2 (findings), but it can't detect that old Sec. 2 moved to new Sec. 3.

This is less of a problem for appropriations bills where accounts match by name ("Military construction, army"), but it affects general legislation where section numbers are the primary structural key.

## Impact

- Renumbered sections show as removed + added instead of modified
- The staffer sees the full old and new text but loses the "what changed within this section" view
- No data is lost, just presented less usefully

## Potential Approaches

### 1. Match by section header text

Use the `<header>` text as a secondary matching key. If Sec. 2 "Sanctions" is removed and Sec. 3 "Sanctions" is added, match them by header.

- Pro: Simple, headers are usually stable across renumbering
- Con: Headers can change too (e.g., "Definitions" is generic and might appear in multiple places)

### 2. Unmatched-node reconciliation pass

After the initial match-by-path pass, take all unmatched (removed + added) nodes and try to pair them by text similarity. If a removed node and an added node have similarity above 0.6, pair them as "moved/modified."

- Pro: Catches renumbering regardless of header text
- Con: O(n*m) comparison on unmatched nodes, could produce false matches if many sections have similar boilerplate

### 3. Hybrid: header match first, then similarity

Try header matching for unmatched nodes first, then fall back to similarity for any still-unmatched nodes.

- Pro: Best of both approaches
- Con: More complex logic

## Recommendation

Start with approach #2 (similarity reconciliation on unmatched nodes). It's the most general and doesn't depend on headers being meaningful. The performance concern is minor since the unmatched set is typically small.

Add a new `change_type` value like `"moved"` or `"renumbered"` to distinguish from regular additions/removals.
