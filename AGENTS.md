# AGENTS.md

Guidelines for AI coding agents working on this repository.

## Quick reference

```bash
uv sync                          # Install dependencies
uv run pytest -m "not slow"     # Fast tests only (~1s)
uv run pytest                    # All tests (needs bills/ XML files)
uv run pytest test_diff_bill.py::TestMatchNodesIntegration  # Single test
```

## Key architecture concepts

- Bill XML has structural containers nested inside titles: `subtitle`, `part`, `chapter`, `subchapter`. These are handled by `_walk_structural_children()` in `bill_tree.py`, which recurses through them to reach sections and appropriations elements.
- `_process_section_element()` is the shared helper for section handling, called from both the main title walk and structural containers.
- `BillNode.division_label` stores the division context (e.g., "Division A: Military Construction"). `normalize_division_title()` strips the letter prefix for matching.
- `match_nodes()` in `diff_bill.py` uses division-aware matching: unique paths pair directly, collision groups (same `match_path` in multiple divisions) are resolved by normalized division title, then text similarity.
- Floor amendment annotations like "(increased by $2,000,000)" reference the **budget request baseline**, not the previous bill version. The base amount in the text IS the correct appropriation. `amounts_changed` compares base amounts (annotations stripped). The `has_amendment_annotations` field on `FinancialChange` flags their presence for informational display.
- Preamble sections (Short Title, References, etc.) sit alongside divisions/titles at the body level and are captured by `walk_body_sections()`.

## Test conventions

- Tests requiring real bill XML files are marked `@pytest.mark.slow`; CI runs only fast tests
- Shared test helpers live in `conftest.py`: `make_bill_node()`, `make_bill_tree()`, `make_node_diff()`, `make_change_dict()`
- Session-scoped fixtures in `conftest.py` cache parsed bill trees and diffs to avoid redundant XML parsing
- `fetch_bills.py` tests use `respx.mock` decorator and monkeypatch `time.sleep`
- `bill_tree.py` tests use inline XML snippets; integration tests use session fixtures
- `test_diff_validation.py` has 278 cross-version diff validation tests: hand-curated correctness assertions plus `TestCorpusDiffSmoke` which runs invariant checks on all 65 adjacent version pairs
- `test_corpus_properties.py` parametrizes over all XML files in `bills/`; uses `_KNOWN_DUPLICATE_COUNTS` and `_KNOWN_MISSING_APPRO` dicts for per-file baselines
- Bill DTD XML uses flat-sibling `appropriations-major/intermediate/small` tags (not nested)
- Dollar amounts are embedded in prose `<text>` elements, extracted via regex
- HTML formatter functions (`word_diff`, `build_financial_table`, etc.) are individually testable
