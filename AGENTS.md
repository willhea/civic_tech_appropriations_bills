# AGENTS.md

Guidelines for AI coding agents working on this repository.

## Quick reference

```bash
uv sync                          # Install dependencies
uv run pytest                    # Run all tests
uv run pytest test_diff_bill.py::TestMatchNodesIntegration  # Single test
```

## Conventions

- `fetch_bills.py` tests use `respx.mock` decorator and monkeypatch `time.sleep`
- `bill_tree.py` tests use inline XML snippets; integration tests skip if real XML files are absent
- `diff_bill.py` tests use helper functions `_node()` and `_tree()` to build fixtures
- Bill DTD XML uses flat-sibling `appropriations-major/intermediate/small` tags (not nested)
- Dollar amounts are embedded in prose `<text>` elements, extracted via regex
- `formatters/html.py` tests use `_change()` and `_sample_diff_dict()` helpers to build fixtures
- HTML formatter functions (`word_diff`, `build_financial_table`, etc.) are individually testable
