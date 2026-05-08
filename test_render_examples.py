"""Smoke test for render_examples.py.

Catches breakage in the rendering APIs (format_html / format_pdf_html /
diff_bills / diff_pdfs) before someone tries to regenerate the committed
examples and discovers the script is rotten. Writes to a temporary
directory so the real examples/ tree is left alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import render_examples


def _has_corpus() -> bool:
    bill_dir = render_examples.BILLS / render_examples.EXAMPLES_TO_RENDER[0].bill_dir
    return bill_dir.exists() and any(bill_dir.glob("*.xml"))


@pytest.mark.skipif(not _has_corpus(), reason="bills corpus not present")
def test_render_examples_main_writes_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(render_examples, "EXAMPLES", tmp_path)
    render_examples.main()

    written = list(tmp_path.glob("*.html"))
    assert written, "expected at least one rendered HTML file"
    for path in written:
        # Anything under a few KB indicates a renderer that bailed out — the
        # real outputs are tens of kilobytes minimum.
        assert path.stat().st_size > 1_000, f"{path} is suspiciously small"
        text = path.read_text()
        assert text.startswith("<!DOCTYPE html>"), f"{path} doesn't look like HTML"
