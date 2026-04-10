# Appropriations Bills

Downloads and parses U.S. appropriations bill text from Congress.gov. Extracts structured financial line items from bill XML for comparing funding across bill versions.

"Appropriations bill" = any bill referred to the House Appropriations Committee (hsap00) or Senate Appropriations Committee (ssap00).

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

### List available text versions

```bash
uv run python fetch_bills.py versions 118 hr 4366
```

Output shows numbered versions with dates:
```
  1. Reported in House (2023-06-27)
  2. Engrossed in House (2023-07-27)
  3. Enrolled Bill (no date)
```

### Download bill versions

```bash
# All versions of a bill
uv run python fetch_bills.py download 118 hr 4366

# Specific version (1-indexed)
uv run python fetch_bills.py download 118 hr 4366 --version 2

# All appropriations bills for a year range
uv run python fetch_bills.py download-all 2024 2026
```

The year range maps to Congress numbers (2024 = 118th, 2025-2026 = 119th), fetches all bills from both appropriations committees, and downloads every text version.

## Parsing Financial Data

`parse_bill.py` extracts dollar amounts from appropriations bill XML and classifies each one. See [methodology.md](methodology.md) for a detailed, non-technical explanation of how amounts are identified and classified.

### Export to CSV

```bash
# Primary allocations only (one amount per account, summable)
uv run python parse_bill.py export output/118-hr-4366/6_enrolled-bill.xml --primary-only -o primary.csv

# All amounts including sub-allocations (detailed view)
uv run python parse_bill.py export output/118-hr-4366/6_enrolled-bill.xml -o detailed.csv

# All versions of a bill to one CSV (for version-to-version comparison)
uv run python parse_bill.py export-all output/118-hr-4366/ --primary-only -o hr4366_versions.csv
```

Use `--primary-only` for clean totals and version comparison. Omit it for detailed sub-allocation data. The CSV includes bill metadata columns (`congress`, `bill_type`, `bill_number`, `version`) so you can filter and pivot by version in a spreadsheet. The `export-all` command concatenates all versions into a single file.

### Python API

```python
from pathlib import Path
from parse_bill import parse_bill

result = parse_bill(Path("output/118-hr-4366/6_enrolled-bill.xml"))
for item in result.items:
    print(f"{item.name}: ${item.amount:,} ({item.amount_type})")
```

### Amount types

Each extracted dollar amount is classified as one of:

| Type | Meaning | Example |
|------|---------|---------|
| `appropriation` | New budget authority | "$2,022,775,000, to remain available" |
| `rescission` | Cancellation of prior funds | "$3,034,205,000 is hereby rescinded" |
| `advance_appropriation` | Funds available in a future fiscal year | "$71,000,000,000... shall become available on October 1, 2024" |
| `proviso_limit` | Sub-allocation ceiling | "not to exceed $398,145,000" |
| `addition_to_prior` | Supplement to prior-year funds | "$15,072,388,000, which shall be in addition to funds previously appropriated" |

### CSV columns

`congress`, `bill_type`, `bill_number`, `version`, `division`, `title`, `major`, `intermediate`, `name`, `amount`, `amount_type`, `section_number`, `element_id`

The `category` tuple from the Python API is flattened into four fixed columns: `division`, `title`, `major`, `intermediate` (empty if not applicable at that level). `raw_text` is omitted from CSV to keep files manageable.

### Data structures (Python API)

`LineItem` fields:
- `amount` (int) - Dollar amount
- `amount_type` (str) - Classification from table above
- `name` (str) - Account/program name from the XML header
- `category` (tuple) - Hierarchy path: division, title, major, intermediate
- `section_number` (str) - Section reference for general provision items
- `element_id` (str) - XML element ID for traceability
- `raw_text` (str) - Full prose text for provenance

`BillLineItems` wraps all items with bill metadata: `congress`, `bill_type`, `bill_number`, `version`.

### How parsing works

The parser walks the Bill DTD XML structure: `<division>` > `<title>` > `appropriations-*` elements. The three appropriations levels (major, intermediate, small) are flat siblings within a title, not nested. The parser tracks context sequentially to build the category hierarchy.

Parenthetical headers like "(INCLUDING TRANSFER OF FUNDS)" inherit the previous sibling's name, since the named element and the text-bearing element are separate siblings.

General provision `<section>` elements are only parsed when they start with appropriation language ("For an additional amount..."). Restriction sections with incidental dollar amounts are skipped.

## Output structure

```
output/
  118-hr-4366/
    1_reported-in-house.xml
    2_engrossed-in-house.xml
    3_enrolled-bill.xml
  119-s-100/
    1_introduced-in-senate.xml
```

## Architecture

Two modules:

- **`fetch_bills.py`** - Downloads bill XML from Congress.gov API v3. Three CLI commands: `versions`, `download`, `download-all`. Uses `congress_for_year()` to map calendar years to Congress numbers.
- **`parse_bill.py`** - Extracts financial line items from downloaded XML. Regex-based dollar amount extraction with keyword-based classification. Public API: `parse_bill(xml_path) -> BillLineItems`.

## Testing

```bash
uv run pytest                    # All tests
uv run pytest test_parse_bill.py # Parser tests only
uv run pytest test_parse_bill.py::TestFullEnrolledBill  # Integration tests
```

- `test_fetch_bills.py`: HTTP mocking with `respx.mock`, `time.sleep` monkeypatched, file I/O uses `tmp_path`
- `test_parse_bill.py`: Inline XML snippets for unit tests, real XML file for integration tests (skipped if file not present)
