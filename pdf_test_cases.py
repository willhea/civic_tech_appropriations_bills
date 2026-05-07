"""Parser for test_data/pdf/118hr8752-changes.md.

Each case in the markdown becomes one PdfTestCase. Used by
test_pdf_test_cases.py and (eventually) by Phase 1+ extractor tests.
See ~/.claude/plans/let-s-put-together-a-snug-twilight.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FIXTURE = Path(__file__).parent / "test_data" / "pdf" / "118hr8752-changes.md"

_CASE_HEADING = re.compile(r"^## Case (\d+) — (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class PdfTestCase:
    number: int
    title: str


def load_cases(path: Path = DEFAULT_FIXTURE) -> list[PdfTestCase]:
    text = path.read_text()
    matches = list(_CASE_HEADING.finditer(text))
    return [PdfTestCase(number=int(m.group(1)), title=m.group(2).strip()) for m in matches]
