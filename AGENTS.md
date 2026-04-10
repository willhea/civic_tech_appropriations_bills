# AGENTS.md

Guidelines for AI coding agents working on this repository.

## Quick reference

```bash
uv sync                          # Install dependencies
uv run pytest                    # Run all tests
uv run pytest test_fetch_bills.py::TestSaveVersion::test_correct_filename  # Single test
```

## Conventions

- `fetch_bills.py` tests use `respx.mock` decorator and monkeypatch `time.sleep`
- `parse_bill.py` tests use inline XML snippets; integration tests skip if real XML files are absent
- Bill DTD XML uses flat-sibling `appropriations-major/intermediate/small` tags (not nested)
- Dollar amounts are embedded in prose `<text>` elements, extracted via regex
