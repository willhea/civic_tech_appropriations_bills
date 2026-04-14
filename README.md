# Bill Diff

Downloads U.S. bill text from Congress.gov and compares versions structurally. Shows what changed between versions: added, removed, modified, and moved sections, with optional financial change filtering.

Works on any bill type (HR, S, HJRES, etc.), not just appropriations.

## Prerequisites

- **Python 3.12+** - Download from https://www.python.org/downloads/ if you don't have it. To check, open a terminal (Terminal on Mac, Command Prompt on Windows) and type `python3 --version`.
- **uv** (Python package manager) - Open a terminal and run:
  - Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

## Quickstart

Generate an HTML report comparing two versions of a bill:

```bash
# 1. Install dependencies (run this once, from the project folder)
uv sync

# 2. Download all versions of a bill
#    Example: HR 4366 from the 118th Congress (2023-2024)
uv run python fetch_bills.py download 118 hr 4366

# 3. Generate an HTML report comparing two versions
uv run python diff_bill.py compare \
  bills/118-hr-4366/1_reported-in-house.xml \
  bills/118-hr-4366/2_engrossed-in-house.xml \
  --format html -o reports/hr4366_v1_vs_v2.html
```

Open the HTML file in any browser to view the comparison. No additional software needed. Reports are saved to the `reports/` folder.

The tool works without an API key using a free demo key (limited to 30 requests per hour). For heavier use, get a free key at https://api.congress.gov/sign-up/ and save it in a file called `.env` in the project folder:

```
CONGRESS_API_KEY=your_key_here
```

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

Files are saved to `bills/<congress>-<type>-<number>/`.

## Comparing Bills

```bash
# Compare two versions (JSON output)
uv run python diff_bill.py compare bills/118-hr-4366/1_reported-in-house.xml bills/118-hr-4366/6_enrolled-bill.xml

# Only sections with dollar amount changes
uv run python diff_bill.py compare old.xml new.xml --financial

# Filter to a specific section
uv run python diff_bill.py compare old.xml new.xml --filter "military construction"

# Include unchanged sections
uv run python diff_bill.py compare old.xml new.xml --include-unchanged

# Save to file
uv run python diff_bill.py compare old.xml new.xml -o diff.json

# Generate a standalone HTML report
uv run python diff_bill.py compare old.xml new.xml --format html -o reports/report.html
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

The tool focuses on substantive changes and ignores formatting differences between bill versions. The following will not be flagged as changes:

- Spacing and line break differences between versions
- Differences in spacing around numbered list markers like (1), (A), or (iv), which vary between House and Senate formatting conventions
- Procedural amendment annotations like "(increased by $103,000,000) (reduced by $103,000,000)" that appear in engrossed versions after floor votes. These are bookkeeping notations, not actual funding changes. The dollar amounts shown in the report reflect the final figures.

## Output Structure

```
bills/
  118-hr-4366/
    1_reported-in-house.xml
    2_engrossed-in-house.xml
    6_enrolled-bill.xml
```

Files are numbered in chronological order. Each number represents a version of the bill as it moved through Congress.

## Bill versions

A bill goes through several versions as it moves through the legislative process. Common versions for appropriations bills:

| Version | What it means |
|---------|--------------|
| introduced-in-house | The bill as originally filed |
| reported-in-house | The bill as approved by committee, before a full House vote |
| engrossed-in-house | The bill as passed by the House, including any floor amendments |
| placed-on-calendar-senate | The House-passed bill placed on the Senate calendar for consideration |
| referred-in-senate | The House-passed bill referred to a Senate committee |
| engrossed-amendment-senate | The Senate's version, often substantially different |
| engrossed-amendment-house | The House's response to the Senate version |
| enrolled-bill | The final text signed into law |

**Which versions to compare:** Adjacent versions (v1 vs v2, v2 vs v3) show what changed in each step of the process. These are the most useful comparisons. Comparing distant versions (v1 vs v6) shows cumulative changes but can be overwhelming, especially when a bill is folded into an omnibus package with hundreds of new sections from other bills.

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

Integration tests use real XML files from `bills/` and skip if not present.
