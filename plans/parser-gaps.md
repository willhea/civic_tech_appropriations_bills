# Parser gaps and known issues

Audit performed 2026-04-15 against 9 enrolled bills and all 56 available versions (113th-118th Congress). Findings from manual analysis, 7 automated agents, and fuzz testing.

## How to use this document

This is the central reference for parser accuracy work. Each issue has a number, priority, root cause, confirmed impact, and test coverage gap. When starting a new session, read this file and the current state of `bill_tree.py`, `diff_bill.py`, and `test_validate_extraction.py` to pick up where we left off.

Issues are grouped by subsystem. Within each group, items are ordered by priority. Items marked **(done)** have been fixed and tested. Items marked **(informational)** are confirmed non-issues but documented for context.

---

## Current test methodology and its limits

### What exists

**Internal unit tests** (59 tests in `test_bill_tree.py`): Test parser mechanics with synthetic XML. Verify path building, context tracking, parenthetical headers, text extraction. Catch logic bugs but don't validate correctness against real bills.

**External validation tests** (6 tests, 414 accounts in `test_validate_extraction.py`): Compare parser output against a hand-curated Excel spreadsheet of Legislative Branch appropriations (FY2014-FY2020). For each line item, the test loads real enrolled bill XML, parses it, finds the node by `match_path`, and checks that the expected dollar amount appears in the node's extracted text. Source spreadsheet: `test_data/House_and_Senate_Appropriations_FY_1994_to_present.xlsx`.

### Overfitting risk

All parser development and validation has been against the same 7 Legislative Branch bills. Every issue found in this audit lives outside that test data:
- Path collisions: absent in Legislative Branch, severe in Defense/Agriculture/Transportation divisions
- 0-node versions: only in 115-hr-244 amendment versions
- Cross-division mismatches: only visible in multi-division diffs
- HTML bugs: only visible in real diff output, not unit tests

Next validation data should come from a jurisdiction we haven't developed against to break the feedback loop.

### Validation test design weaknesses

**"Amount in node" is a weak assertion.** The test checks `expected_amount in extract_amounts(node.body_text)`. 32 of 414 fixture amounts also appear in unrelated nodes elsewhere in the same bill (e.g., $300,000 for Senate mail costs also appears in Corps of Engineers and Forest Service nodes). A parser bug that routed text to the wrong node could pass undetected.

**Multiple line items sharing one node hides granularity failures.** 8 House Leadership entries (Speaker, Majority Leader, etc.) all point to the same `house leadership offices` node. The test passes because all 8 amounts appear in one text block. The parser can't break these into separate nodes because the XML doesn't separate them, but a diff shows the entire block as modified even if only one sub-item changed. The test can't distinguish "correctly parsed 8 items" from "dumped 8 items into one blob."

**No cross-version diff tests against external data.** The validation tests parse individual bills. No test verifies correct node pairing or change detection between versions.

**Narrow jurisdiction coverage.** All 414 entries are Legislative Branch. The other 11 subcommittee jurisdictions have no external validation and have more complex structures.

### Strategies for testing without external data

**Property-based tests (no external data needed, highest value):**
- Every `$X` in the raw XML should appear in exactly one node's body_text (or be in a `<quote>` element). Run against all 56 versions.
- No two nodes should have the same `match_path` (flag violations as known limitation).
- Total character count across all nodes should be within some percentage of total XML text content.
- Every `appropriations-*` element with text content should produce a node.

**Self-consistency tests:**
- Parsing the same bill twice should produce identical results.
- Nearly-identical version pairs (e.g., engrossed-amendment-house vs enrolled, which often differ by a few lines) should produce very few diff changes. Assert upper bounds without knowing exact changes.

**Structural coverage tests:**
- Scan the corpus for every unique XML tag/structure pattern. Verify the parser has a code path for each. The subtitle and amendment-block/legis-body issues were both discoverable this way.

**Held-out validation:**
- When external data becomes available, don't use it for development. Use it only to measure accuracy on first run, then fix issues iteratively.

**Crowdsourced spot-checks:**
- Generate HTML reports for bills staffers know well. Each flag becomes a new fixture entry.

---

## Parser issues

### 1. Cross-division path collisions cause wrong diffs (done)

Every omnibus bill has dozens of duplicate `match_path` values. Examples from 114-hr-2029: 90 duplicate paths out of 2,227 nodes.

Common causes:
- `('general provisions',)` x5-8: multiple divisions each have "General Provisions" titles, but match_path strips division labels
- `('general provisions', 'sec. 501')` x4-5: same section number reused across divisions
- `('bilateral economic assistance', 'funds appropriated to the president')` x6-9: same header in different divisions

Root cause: `match_path` deliberately excludes division labels (to support matching across versions where division letters change), but this creates ambiguity for nodes with identical titles in different divisions.

**Confirmed impact**: Diffing 118-hr-4366 v4 (Senate amendment) to v5 (House amendment) produces **226 cross-division mismatches**. Nodes from Division B (Agriculture) paired with Division A (Military Construction). The diff tool's `match_nodes()` in `diff_bill.py` groups by `match_path` and pairs positionally, so reordered/added/removed divisions produce arbitrary pairings.

**Key files**: `bill_tree.py` (`_build_paths`, line 93), `diff_bill.py` (`match_nodes`)

**Test coverage gap**: Validation fixture has 0 path collisions. No cross-version matching tests.

### 2. Amendment-doc versions with `legis-body` wrapper produce 0 nodes (done)

Two versions of 115-hr-244 produce 0 nodes:
- `4_engrossed-amendment-senate.xml`: empty amendment-block (0 chars, legitimate)
- `5_engrossed-amendment-house.xml`: 8 sections, 6,917 chars of content, **completely invisible to parser**

Root cause: Parser finds `amendment-block` via `find_bill_body()`, then looks for divisions/titles/sections as direct children. But structure is `amendment-block > legis-body > section`. The intermediate `legis-body` wrapper causes total miss.

**Key files**: `bill_tree.py` (`find_bill_body`, line 38; `normalize_bill`, line 422)

**Test coverage gap**: No test covers amendment-block with nested legis-body.

### 3. `_extract_section_text` loses subsection content (done)

When a section has BOTH a direct `<text>` child AND `<subsection>` children, only `<text>` content is returned. Found 2 instances in 116-hr-1865 (out of 1,525 sections):
- Sec. 788: captures 97 chars instead of 1,096
- Sec. 142: captures 471 chars instead of 947

Fix: combine direct `<text>` with subsection content instead of preferring one.

**Key files**: `bill_tree.py` (`_extract_section_text`, line 321)

**Test coverage gap**: No unit test covers text+subsection. Affected sections don't contain fixture amounts.

### 4. Dollar amount gap (~5% raw, ~1-2% real) (medium priority)

116-hr-1865: 2,286 raw vs 2,156 parsed (130 gap, 5.7%). 118-hr-4366: 1,724 vs 1,645 (79 gap, 4.6%).

Breakdown (116-hr-1865): 80 in `<quote>` elements (correct to skip), 22 in deeply nested `<clause>`/`<subclause>`, ~28 scattered.

**Test coverage gap**: No test measures amount coverage ratio.

### 5. 72 nodes have repeated dollar amounts (medium priority)

In 116-hr-1865, 72 nodes have the same amount appearing more than once. 77 legitimate (different contexts), 3 suspicious (identical surrounding text, likely extraction overlap).

**Test coverage gap**: No test checks for extraction duplication.

### 6. `<subtitle>` elements silently skipped (low priority)

42 occurrences across corpus. `walk_title()` ignores `<subtitle>` tags. Unknown whether subtitles contain appropriations data.

**Key files**: `bill_tree.py` (`walk_title`, line 218)

### 7. Mixed body-level structures (low priority)

Some bills have sections AND divisions AND titles as siblings under `legis-body`. Parser's three-shape detection means preamble sections lost when divisions also exist. Affects opening enacting clause, typically not dollar amounts.

**Key files**: `bill_tree.py` (`normalize_bill`, line 422)

### 8. Empty header clobbers `prev_name` (low priority)

Empty header on intermediate/small sets `prev_name = ""`. Subsequent parenthetical sibling inherits "" instead of last real name. Confirmed in synthetic XML, 0 empty headers in real enrolled bills.

**Key files**: `bill_tree.py` (`_process_appro_element`, line 165)

---

## Diff pipeline issues

### 9. Positional pairing breaks on structural changes (done)

`match_nodes()` groups by `match_path` and pairs by array index. When group sizes differ between versions (divisions added/removed/reordered), pairings become arbitrary. Compounds with issue #1.

The 0.4 similarity threshold partially mitigates by splitting dissimilar pairs into "removed"/"added", but doesn't help with similar boilerplate across divisions.

**Key files**: `diff_bill.py` (`match_nodes`), `reconcile.py`

### 10. Floor amendment annotation stripping hides real financial changes (done)

`extract_amounts` strips `(increased by $X)` / `(reduced by $X)` annotations before extracting amounts. This prevents the annotation amount from being counted as a separate line item (correct), but the side effect is that the diff reports `amounts_changed: False` even when floor amendments changed the effective appropriation.

**Confirmed impact**: HR-4366 v1->v2 (reported to engrossed), Board of Veterans Appeals: v1 has `$287,000,000`, v2 has `$287,000,000 (increased by $2,000,000)`. The tool says nothing changed financially, but the effective amount went from $287M to $289M. **14 sections affected** in just this one version pair.

The tool needs to either compute effective amounts (base + increases - decreases) or at minimum flag that amendment annotations are present.

**Key files**: `diff_bill.py` (`_AMENDMENT_RE`, `extract_amounts`)

### 11. Section renumbering causes cascading mismatches (done)

When a new section is inserted mid-bill, all subsequent sections get renumbered (e.g., old sec. 223 becomes new sec. 224). Since `match_path` includes section numbers, every renumbered section becomes a false mismatch.

**Confirmed impact**: HR-4366 v3->v4, VA Administrative Provisions. A new sec. 223 was inserted, pushing 30+ sections up by 1. The similarity threshold (0.4) correctly splits the false matches, and `reconcile_moves` re-pairs most with 1.0 similarity. But sections near the move threshold (0.7) fall through: v3 sec. 236 -> v4 sec. 237 has 0.682 similarity (modified AND renumbered), so it appears as separate "removed"/"added" instead of one "moved+modified" change.

**Dead zone**: 15 removed/added pairs in this diff fall in the 0.5-0.7 range (above the split threshold but below the move threshold) and are never re-paired.

**Key files**: `diff_bill.py` (`_SIMILARITY_THRESHOLD = 0.4`, `_MOVE_THRESHOLD = 0.7`), `reconcile.py`

### 12. Version-to-version node count instability (informational)

Node counts vary dramatically: 115-hr-244 goes from 7 (introduced) to 2,103 (enrolled). Early versions are **shell bills**: short procedural placeholders (a title and a few sections) that Congress later replaces entirely with the real legislative text. They serve as vehicles for the full omnibus content added during the amendment process. Shell bills typically have 5-10 nodes, 0 divisions, and 1-2 dollar amounts.

Diffing shell versions against full versions produces mass "removed"/"added" with no useful matching. Arguably correct but not communicated to users. Property tests skip dollar coverage measurement on shell bills (< 3 amounts) since missing 1 of 1 is noise, not a meaningful accuracy signal.

---

## HTML report bugs

### 15. Double-escaping in financial table paths (done)

`formatters/html.py` line 72: `escape(" > ".join(path_parts))` double-escapes `>` into `&amp;gt;`. Users see literal `&gt;` in every financial table row. Fix pattern exists at line 154.

**Key files**: `formatters/html.py` (line 72)

### 16. Financial table CSS coloring breaks on sub-rows

`nth-child(4)` and `nth-child(5)` CSS selectors target wrong cells in sub-rows where `rowspan` reduces the `<td>` count.

**Key files**: `formatters/html.py` (lines 316-317)

### 17. Table sort JS breaks rowspan grouping

Sort function reorders `<tr>` independently, separating parent rows from sub-rows.

**Key files**: `formatters/html.py` (lines 386-404)

### 18. Summary bar count mismatch with `--financial` / `--filter` (done)

Filtered changes use unfiltered summary counts. Summary claims more changes than are displayed.

**Key files**: `diff_bill.py` (lines 500-530)

### 19. Moved cards suppress body text

When `old_text == new_text`, moved cards show only path change, no content. 26 of 34 moved sections in a real diff have no visible body text.

**Key files**: `formatters/html.py` (line 229)

---

## Amount extraction findings (verified, no action needed)

- `extract_amounts` regex and annotation filter work correctly for all real patterns
- Trillions handled (sanity test caps at $999B, would need update if trillion amounts appear)
- Decimal truncation (`$1,234.56` -> 1,234) is a non-issue (no decimals in real bills)
- Floor amendment annotations correctly stripped in PCS/engrossed versions (0 found in enrolled bills, which is expected)
- 194 appropriations elements with paragraph children confirmed across corpus, validating the `_extract_appropriations_text` fix
- 1,590 parenthetical headers all correctly classified, no false positives
- 0 nested appropriations elements in corpus, flat-sibling assumption holds
- `extract_text_content` via `itertext()` prevents amounts from splitting across XML elements

---

## Validation coverage summary

| Metric | Value |
|--------|-------|
| Validated line items | 414 |
| Bills covered | 7 enrolled (FY2014-FY2020) |
| Chambers | Both (153 Senate, 261 House) |
| Subcommittee jurisdictions validated | 1 of 12 (Legislative Branch only) |
| Untestable items (no standalone dollar figure) | 9 |
| Cross-version diff validation | None |
| Amount uniqueness (appear in only one node) | 382 of 414 (92%) |
| Bill versions producing 0 nodes | 2 (115-hr-244 v4, v5) |
| Bill versions in corpus | 56 total, all parse without errors |
| Appropriations elements with paragraph children | 194 across corpus |

---

## Property test baselines (2026-04-15)

Recorded after Part A property tests completed. 63 XML versions across 12 bills. Tests in `test_corpus_properties.py`.

**Dollar coverage** (amounts in raw XML found in parsed nodes, excluding quote/header):
- 1.000: 115-hr-5895/v1, 116-hr-1865/v1-v3, 118-hr-8752/v1-v2 (6 files)
- 0.95-0.99: most enrolled/omnibus versions (20 files)
- 0.90-0.95: 114-hr-2029/v1-v4, 118-hr-4366/v2-v3, 118-hr-8774/v2-v3 (7 files)
- 0.80-0.90: 113-hr-3547/v6 (0.826), 118-hr-4366/v1 (0.843), 115-hr-5895/v5 (0.845), 118-hr-8774/v1 (0.817) (4 files)
- n/a (no amounts or 0 nodes): 27 files
- Floor threshold: 0.80

**Duplicate match_paths** (cross-division collisions):
- 19 files have duplicates, range 2-156
- Worst: 114-hr-2029/v6-v7 (156 each), 115-hr-1625/v7 (153), 113-hr-3547/v5 (150)
- 44 files have zero duplicates

**Appropriations element coverage** (elements with text that map to nodes):
- 31 files: all elements found (0 missing)
- 113-hr-3547/v6: 310/1072 missing (29%)
- 115-hr-5895/v5: 33/178 missing (19%)
- 30 files: no appropriations elements (skipped)

**Character coverage ratio** (node chars / raw body chars, excluding quote/header/enum):
- 0.95-1.05: most full bills (34 files)
- 0.80-0.95: some omnibus enrolled versions
- 0.60-0.80: shell bills with few nodes (115-hr-1625/v1-v5, 118-hr-8282, 113-hr-3547/v6)
- 0.10-0.60: 118-hr-2882/v1 (0.448), 116-hr-1865/v4 (0.125)
- >1.0: small bills where node text exceeds raw (whitespace normalization)
- Floor threshold: 0.10

---

## Suggested work order

Priority is based on user impact (staffers reading reports) and feasibility.

1. **Property-based tests** (issues #1, #2, #4): Add tests that run against the full 56-version corpus without needing external data. Catches regressions and surfaces structural gaps. Highest value per effort.
2. **Fix amendment-doc legis-body wrapper** (issue #2): Simple fix, complete content loss on affected versions.
3. **Fix _extract_section_text subsection loss** (issue #3): Simple fix, rare but real data loss.
4. **Fix floor amendment annotation handling** (issue #10): Either compute effective amounts or flag annotations as present. Currently hides real financial changes from users.
5. **HTML double-escaping and summary mismatch** (issues #15, #18): User-facing bugs, straightforward fixes.
6. **Path collision and pairing strategy** (issues #1, #9, #11): Requires design work. Options: incorporate division into match_path with fallback, use text similarity as secondary signal, adjust dead zone between 0.4/0.7 thresholds, header-based matching for renumbered sections.
7. **External validation from a different jurisdiction**: Acquire or build a spreadsheet for Defense or Labor-HHS. Run parser against it without modifying code first for true accuracy baseline.
8. **Remaining HTML issues** (issues #16, #17, #19): Lower priority, edge cases in report display.
