# Appropriations Bill Text Downloader

Downloads appropriations bill text versions from Congress.gov in XML format for comparing differences between versions. "Appropriations bill" = any bill referred to the House Appropriations Committee (hsap00) or Senate Appropriations Committee (ssap00).

## Setup

```bash
uv sync
```

Copy your API key into `.env`:

```
CONGRESS_API_KEY=your_key_here
```

Get a free key at https://api.congress.gov/sign-up/. The script falls back to the demo key (30 req/hr) if no key is set.

## Usage

### List available text versions for a bill

```bash
uv run python fetch_bills.py versions 118 hr 4366
```

Output shows numbered versions with dates:
```
  1. Reported in House (2023-06-27)
  2. Engrossed in House (2023-07-27)
  3. Enrolled Bill (no date)
```

### Download a specific version

```bash
uv run python fetch_bills.py download 118 hr 4366 --version 2
```

### Download all versions of a bill

```bash
uv run python fetch_bills.py download 118 hr 4366
```

### Download all appropriations bills for a year range

```bash
uv run python fetch_bills.py download-all 2024 2026
```

This maps the year range to Congress numbers (2024 = 118th, 2025-2026 = 119th), fetches all bills from both appropriations committees for those congresses, and downloads every text version.

## Output structure

Downloaded XML files are saved to `output/` with this structure:

```
output/
  118-hr-4366/
    1_reported-in-house.xml
    2_engrossed-in-house.xml
    3_enrolled-bill.xml
  119-s-100/
    1_introduced-in-senate.xml
```

## How it works

1. Queries the Congress.gov API v3 `/bill/{congress}/{type}/{number}/text` endpoint to list text versions
2. Downloads XML format of each version directly from congress.gov
3. Saves files with version index and type for easy ordering and identification
4. For bulk downloads (`download-all`), fetches all bills from both House and Senate Appropriations Committee endpoints, filters by Congress number, and downloads all text versions
