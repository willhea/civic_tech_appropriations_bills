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
```

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

## Output Structure

```
output/
  118-hr-4366/
    1_reported-in-house.xml
    2_engrossed-in-house.xml
    6_enrolled-bill.xml
```

## Architecture

Three modules:

- **`fetch_bills.py`** - Downloads bill XML from Congress.gov API v3. CLI commands: `versions`, `download`, `download-all`.
- **`bill_tree.py`** - Normalizes bill XML into a `BillTree` of `BillNode` objects. Handles three structural shapes: with divisions, with titles only, and flat sections.
- **`diff_bill.py`** - Compares two `BillTree`s. Matches sections by normalized header path, detects false matches via text similarity, reconciles moved sections, and extracts dollar amounts for financial filtering.

## Testing

```bash
uv run pytest                          # All tests
uv run pytest test_bill_tree.py        # Normalization tests
uv run pytest test_diff_bill.py        # Diff/matching tests
uv run pytest test_financial_diff.py   # Financial filtering tests
uv run pytest test_reconcile.py        # Section move detection tests
```

Integration tests use real XML files from `output/` and skip if not present.
