# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                          # Install dependencies
uv run pytest                    # Run all tests
uv run pytest test_fetch_bills.py::TestSaveVersion::test_correct_filename  # Single test
```

### CLI usage

```bash
# List available text versions for a bill
uv run python fetch_bills.py versions 118 hr 4366

# Download all versions of a bill (XML)
uv run python fetch_bills.py download 118 hr 4366

# Download specific version (1-indexed)
uv run python fetch_bills.py download 118 hr 4366 --version 3

# Download all appropriations bills for a year range
uv run python fetch_bills.py download-all 2024 2026
```

## Architecture

Single-module app (`fetch_bills.py`) that downloads appropriations bill text versions from the Congress.gov API v3 in XML format for downstream diff/comparison.

**Three commands:** `versions` (list available text versions), `download` (single bill), `download-all` (bulk by year range).

**API flow:** The text endpoint `/bill/{congress}/{type}/{number}/text` returns `textVersions`, each with format URLs. XML URLs are fetched directly (not through `api_get`) since they're congress.gov content, not API calls.

**Year mapping:** `congress_for_year()` converts calendar years to Congress numbers. `download-all` computes the set of congresses for a year range, fetches all bills from both appropriations committees, filters by congress, then downloads all text versions.

**Output structure:** `output/{congress}-{type}-{number}/{index}_{sanitized-version-type}.xml`

**API key:** Loaded from `CONGRESS_API_KEY` in `.env`, falls back to `DEMO_KEY` (30 req/hr).

## Testing

Tests use `respx.mock` decorator for HTTP mocking. All tests monkeypatch `time.sleep` to prevent real sleeps. File I/O tests use pytest's `tmp_path` fixture.
