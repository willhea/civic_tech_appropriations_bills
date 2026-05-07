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

Location = tuple[int, int, int, int]

_CASE_HEADING = re.compile(r"^## Case (\d+) — (.+)$", re.MULTILINE)
_TYPE_LINE = re.compile(r"^\*\*Type:\*\*\s+(\w+)", re.MULTILINE)
_V1_LOCATION_LINE = re.compile(r"^\*\*V1 location:\*\*\s+(.+?)\s*$", re.MULTILINE)
_V2_LOCATION_LINE = re.compile(r"^\*\*V2 location:\*\*\s+(.+?)\s*$", re.MULTILINE)
_LOCATION_RANGE = re.compile(r"p\.(\d+)\s+L(\d+)\s*[–-]\s*p\.(\d+)\s+L(\d+)")
_V1_TEXT_BLOCK = re.compile(r"\*\*V1 text:\*\*\s*\n```\n(.*?)\n```", re.DOTALL)
_V2_TEXT_BLOCK = re.compile(r"\*\*V2 text:\*\*\s*\n```\n(.*?)\n```", re.DOTALL)
_PLACEHOLDER_TEXT = re.compile(r"^\(none\s+[—-]\s+(added|removed) in v2\)$")


@dataclass(frozen=True)
class PdfTestCase:
    number: int
    title: str
    change_type: str
    v1_location: Location | None
    v2_location: Location | None
    v1_text: str
    v2_text: str


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
                v1_location=_parse_location(body, _V1_LOCATION_LINE),
                v2_location=_parse_location(body, _V2_LOCATION_LINE),
                v1_text=_parse_text(body, _V1_TEXT_BLOCK),
                v2_text=_parse_text(body, _V2_TEXT_BLOCK),
            )
        )
    return cases


def _parse_type(body: str) -> str:
    m = _TYPE_LINE.search(body)
    if not m:
        raise ValueError("missing **Type:** line")
    return m.group(1).lower().strip()


def _parse_location(body: str, line_regex: re.Pattern[str]) -> Location | None:
    m = line_regex.search(body)
    if not m:
        raise ValueError(f"missing location line for pattern {line_regex.pattern}")
    value = m.group(1).strip()
    if value.startswith("N/A"):
        return None
    range_match = _LOCATION_RANGE.search(value)
    if not range_match:
        raise ValueError(f"unparseable location: {value!r}")
    return tuple(int(g) for g in range_match.groups())  # type: ignore[return-value]


def _parse_text(body: str, block_regex: re.Pattern[str]) -> str:
    m = block_regex.search(body)
    if not m:
        raise ValueError(f"missing text block for pattern {block_regex.pattern}")
    raw = m.group(1).strip()
    if _PLACEHOLDER_TEXT.match(raw):
        return ""
    return raw
