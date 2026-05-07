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
_TYPE_LINE = re.compile(r"^\*\*Type:\*\*\s+(\w+)", re.MULTILINE)


@dataclass(frozen=True)
class PdfTestCase:
    number: int
    title: str
    change_type: str


def load_cases(path: Path = DEFAULT_FIXTURE) -> list[PdfTestCase]:
    text = path.read_text()
    headings = list(_CASE_HEADING.finditer(text))
    cases = []
    for i, m in enumerate(headings):
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end]
        cases.append(
            PdfTestCase(
                number=int(m.group(1)),
                title=m.group(2).strip(),
                change_type=_parse_type(body),
            )
        )
    return cases


def _parse_type(body: str) -> str:
    m = _TYPE_LINE.search(body)
    if not m:
        raise ValueError("missing **Type:** line")
    return m.group(1).lower().strip()
