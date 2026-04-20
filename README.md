# Bill Diff

Downloads U.S. bill text from Congress.gov and compares versions structurally. Shows what changed between versions: added, removed, modified, and moved sections, with optional financial change filtering.

Works on any bill type (HR, S, HJRES, etc.), not just appropriations.

**See it in action:** [Committee vs. Floor](https://willhea.github.io/civic_tech_appropriations_bills/hr4366_committee_vs_floor.html) | [House vs. Senate](https://willhea.github.io/civic_tech_appropriations_bills/hr4366_house_vs_senate.html) (example reports for HR 4366, 118th Congress)

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

`--format html` produces a self-contained HTML file that can be opened in any browser with no install or server required. See [examples/](examples/) for sample reports you can open immediately. The report includes:

- **Header** with bill number, congress, and version numbers (e.g., "v1: reported-in-house → v2: engrossed-in-house")
- **Sidebar** listing all changed sections with color-coded change type badges. Type in the filter box to narrow the list. Click any item to jump to that section.
- **Financial summary table** showing dollar amounts before and after, with change amounts and percentages. Click column headers to sort. Click a row to jump to that section's detail. Sections with floor amendment annotations show a warning badge.
- **Change cards** for each modified, added, removed, or moved section. Modified sections show word-level inline diffs: additions highlighted in green, deletions in red strikethrough. Moved sections show both the old and new location, plus body text.
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

Floor amendment annotations like "(increased by $2,000,000)" appear in engrossed versions after floor votes. These annotations reference the budget request baseline, not the previous bill version, so the base amount in the text is the authoritative appropriation. The tool strips the annotations before comparing amounts across versions, then flags their presence with an informational badge in the HTML report so readers can see where the floor acted.

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
- **`bill_tree.py`** - Normalizes bill XML into a `BillTree` of `BillNode` objects. Handles divisions, titles, and flat sections, plus structural containers within titles (subtitle, part, chapter, subchapter). Captures preamble sections that sit alongside divisions or titles.
- **`diff_bill.py`** - Compares two `BillTree`s. Uses division-aware matching for omnibus bills (resolves cross-division path collisions by normalized division title). Detects false matches via text similarity, reconciles moved sections, and extracts dollar amounts (stripping floor amendment annotations before comparison, flagging their presence separately).
- **`formatters/html.py`** - Generates standalone HTML reports from diff output with sidebar navigation, financial summary table, and word-level inline diffs.

## Testing

```bash
uv run pytest -m "not slow"               # Fast unit tests (~1s, no XML files needed)
uv run pytest                              # All tests (needs bills/ XML files)
uv run pytest test_bill_tree.py            # Normalization tests
uv run pytest test_diff_bill.py            # Diff/matching tests
uv run pytest test_financial_diff.py       # Financial filtering tests
uv run pytest test_reconcile.py            # Section move detection tests
uv run pytest test_format_html.py          # HTML report formatter tests
uv run pytest test_corpus_properties.py    # Corpus-wide property tests
uv run pytest test_validate_extraction.py  # External validation tests
```

Tests that require real bill XML files are marked `@pytest.mark.slow`. The fast suite (`-m "not slow"`) runs 218 unit tests using inline XML and mocked data. CI runs the fast suite automatically on every PR.

Integration tests use real XML files from `bills/` and skip if not present. To run the full suite including validation tests, download the required bills:

```bash
source .env  # load API key
uv run python fetch_bills.py download 118 hr 4366
uv run python fetch_bills.py download 118 hr 2882
uv run python fetch_bills.py download 118 hr 8282
uv run python fetch_bills.py download 118 hr 8752
uv run python fetch_bills.py download 118 hr 8774
uv run python fetch_bills.py download 118 hr 4820
uv run python fetch_bills.py download 117 hr 2471
uv run python fetch_bills.py download 117 hr 4432
uv run python fetch_bills.py download 117 hr 4502
uv run python fetch_bills.py download 116 hr 1865
uv run python fetch_bills.py download 116 hr 133
uv run python fetch_bills.py download 115 hr 5895
uv run python fetch_bills.py download 115 hr 1625
uv run python fetch_bills.py download 115 hr 244
uv run python fetch_bills.py download 114 hr 2029
uv run python fetch_bills.py download 113 hr 83
uv run python fetch_bills.py download 113 hr 3547
```

The validation tests compare 414 extracted line items across 7 Legislative Branch bills (FY2014-FY2020) against amounts from a curated appropriations spreadsheet. The corpus property tests (`test_corpus_properties.py`) check dollar coverage, path uniqueness, and character coverage across all downloaded bills.
