# Bill Diff

Downloads U.S. bill text from Congress.gov and compares versions structurally. Shows what changed between versions: added, removed, modified, and moved sections, with optional financial change filtering.

Works on any bill type (HR, S, HJRES, etc.), not just appropriations.

## Setup

```bash
uv sync
```

Copy your API key into `.env`:

```
CONGRESS_API_KEY=your_key_here
```

Get a free key at https://api.congress.gov/sign-up/. The script falls back to the demo key (30 req/hr) if no key is set.

## Downloading Bills

```bash
# List available text versions
uv run python fetch_bills.py versions 118 hr 4366

# Download all versions of a bill
uv run python fetch_bills.py download 118 hr 4366

# Download a specific version (1-indexed)
uv run python fetch_bills.py download 118 hr 4366 --version 2

# Download all appropriations bills for a year range
uv run python fetch_bills.py download-all 2024 2026
```

Files are saved to `output/<congress>-<type>-<number>/`.

## Comparing Bills

```bash
# Compare two versions (JSON output)
uv run python diff_bill.py compare output/118-hr-4366/1_reported-in-house.xml output/118-hr-4366/6_enrolled-bill.xml

# Only sections with dollar amount changes
uv run python diff_bill.py compare old.xml new.xml --financial

# Filter to a specific section
uv run python diff_bill.py compare old.xml new.xml --filter "military construction"

# Include unchanged sections
uv run python diff_bill.py compare old.xml new.xml --include-unchanged

# Save to file
uv run python diff_bill.py compare old.xml new.xml -o diff.json

# Generate a standalone HTML report
uv run python diff_bill.py compare old.xml new.xml --format html -o report.html
```

### HTML report

`--format html` produces a self-contained HTML file that can be opened in any browser with no install or server required. The report includes:

- **Header** with bill number, congress, and version numbers (e.g., "v1: reported-in-house → v2: engrossed-in-house")
- **Sidebar** listing all changed sections with color-coded change type badges. Type in the filter box to narrow the list. Click any item to jump to that section.
- **Financial summary table** showing dollar amounts before and after, with change amounts and percentages. Click column headers to sort. Click a row to jump to that section's detail.
- **Change cards** for each modified, added, removed, or moved section. Modified sections show word-level inline diffs: additions highlighted in green, deletions in red strikethrough. This highlights exactly which words changed (typically dollar amounts) rather than showing the entire paragraph as changed.
- **Prev/next buttons** in the bottom right corner to step through changes one at a time.

When no changes are detected between versions, the report displays "No changes found" rather than a blank page.

Financial data is automatically included in the HTML report without needing the `--financial` flag.

### Change types

| Type | Meaning |
|------|---------|
| `modified` | Section exists in both versions, text changed |
| `added` | Section only in new version |
| `removed` | Section only in old version |
| `moved` | Section relocated (renumbered or moved under a different title) |
| `unchanged` | Identical text in both versions (hidden by default) |

### Financial filtering

`--financial` filters to sections where dollar amounts changed and adds amount details to the JSON output. Sections where text changed but amounts stayed the same are excluded.

### Text normalization

The tool normalizes bill text before comparing so that formatting differences between versions don't appear as substantive changes. The following will not show up as modifications:

- **Whitespace differences.** Runs of spaces, tabs, and newlines are collapsed to single spaces. Different XML formatting between versions is invisible.
- **List marker spacing.** House and Senate versions sometimes differ in whether there's a space before parenthetical list markers like `(1)`, `(A)`, `(iv)`. For example, `and (2)adheres` vs `and(2)adheres`. These are formatting conventions with no legal significance and are normalized out.
- **Amendment annotations.** Engrossed bill versions (the text after a floor vote) contain procedural annotations recording adopted amendments, e.g., `$1,517,455,000 (increased by $103,000,000) (reduced by $103,000,000)`. These `(increased by $X)` and `(reduced by $X)` parentheticals are bookkeeping, not actual appropriation amounts. The base amount already reflects the final figure. The tool strips these before comparing dollar amounts so they don't create phantom financial changes.

## Output Structure

```
output/
  118-hr-4366/
    1_reported-in-house.xml
    2_engrossed-in-house.xml
    6_enrolled-bill.xml
```

## Architecture

Four modules:

- **`fetch_bills.py`** - Downloads bill XML from Congress.gov API v3. CLI commands: `versions`, `download`, `download-all`.
- **`bill_tree.py`** - Normalizes bill XML into a `BillTree` of `BillNode` objects. Handles three structural shapes: with divisions, with titles only, and flat sections.
- **`diff_bill.py`** - Compares two `BillTree`s. Matches sections by normalized header path, detects false matches via text similarity, reconciles moved sections, and extracts dollar amounts for financial filtering.
- **`formatters/html.py`** - Generates standalone HTML reports from diff output with sidebar navigation, financial summary table, and word-level inline diffs.

## Testing

```bash
uv run pytest                          # All tests
uv run pytest test_bill_tree.py        # Normalization tests
uv run pytest test_diff_bill.py        # Diff/matching tests
uv run pytest test_financial_diff.py   # Financial filtering tests
uv run pytest test_reconcile.py        # Section move detection tests
uv run pytest test_format_html.py      # HTML report formatter tests
```

Integration tests use real XML files from `output/` and skip if not present.
