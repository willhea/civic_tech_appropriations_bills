"""Unit tests for the format-agnostic line classifier."""

from __future__ import annotations

import pytest

from parsers.classifier import (
    StyleHints,
    Tag,
    classify,
    has_trailing_amount,
    is_all_caps,
    parse_division,
    parse_run_in_header,
    parse_section,
    parse_title,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("DEPARTMENT OF DEFENSE", True),
        ("Department of Defense", False),
        ("DRAFT", True),
        ("(a)", False),
        ("", False),
    ],
)
def test_is_all_caps(text, expected):
    assert is_all_caps(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("...the sum of $1,234,567,000.", True),
        ("...$500,000", True),
        ("$25.50", True),
        ("text without money", False),
        ("$1,234 plus more text", False),
    ],
)
def test_has_trailing_amount(text, expected):
    assert has_trailing_amount(text) is expected


@pytest.mark.parametrize(
    "text,enum,header",
    [
        ("DIVISION A—DEFENSE APPROPRIATIONS", "A", "DEFENSE APPROPRIATIONS"),
        ("DIVISION B--LABOR-HHS", "B", "LABOR-HHS"),
        ("DIVISION 1—FIRST", "1", "FIRST"),
    ],
)
def test_parse_division(text, enum, header):
    assert parse_division(text) == (enum, header)


def test_parse_division_rejects_non_division():
    assert parse_division("TITLE I—SOMETHING") is None


@pytest.mark.parametrize(
    "text,enum,header",
    [
        ("TITLE I—MILITARY PERSONNEL", "I", "MILITARY PERSONNEL"),
        ("TITLE IV—FOO", "IV", "FOO"),
        ("TITLE 1—NUMERIC TITLE", "1", "NUMERIC TITLE"),
    ],
)
def test_parse_title(text, enum, header):
    assert parse_title(text) == (enum, header)


@pytest.mark.parametrize(
    "text,enum,header",
    [
        ("SEC. 101. SHORT TITLE.", "101", "SHORT TITLE."),
        ("SEC. 7A. SOMETHING.", "7A", "SOMETHING."),
        ("SECTION 1.", "1", ""),
    ],
)
def test_parse_section(text, enum, header):
    assert parse_section(text) == (enum, header)


def test_parse_run_in_header_basic():
    assert parse_run_in_header("SALARIES AND EXPENSES.—For necessary expenses of the foo, $1,000.") == (
        "SALARIES AND EXPENSES",
        "For necessary expenses of the foo, $1,000.",
    )


def test_parse_run_in_header_returns_none_for_non_runin():
    assert parse_run_in_header("This is just a regular sentence.") is None


def test_classify_division():
    hints = StyleHints(centered=True, all_caps=True)
    assert classify("DIVISION A—DEFENSE APPROPRIATIONS", hints) is Tag.DIVISION


def test_classify_division_rejected_when_not_centered():
    # When the source explicitly tells us a line is not centered, a
    # DIVISION-shaped sentence in body text shouldn't be misclassified.
    hints = StyleHints(centered=False, all_caps=False)
    # Use a phrase that contains the word DIVISION but not the heading shape.
    assert classify("DIVISION A—DEFENSE APPROPRIATIONS", hints) is Tag.BODY


def test_classify_title():
    hints = StyleHints(centered=True, all_caps=True)
    assert classify("TITLE I—MILITARY PERSONNEL", hints) is Tag.TITLE


def test_classify_section_regardless_of_layout():
    # SEC. N. is unambiguous; layout shouldn't matter.
    assert classify("SEC. 101. SHORT TITLE.") is Tag.SECTION
    assert classify("SECTION 7. FOO.", StyleHints(indent_level=0)) is Tag.SECTION


def test_classify_appropriations_major():
    hints = StyleHints(centered=True, all_caps=True, indent_level=0)
    assert classify("DEPARTMENT OF DEFENSE—MILITARY", hints) is Tag.APPRO_MAJOR


def test_classify_appropriations_major_skips_single_word():
    # Single all-caps tokens must not be classified as headings; they
    # are usually leftover watermark fragments.
    hints = StyleHints(centered=True, all_caps=True)
    assert classify("DRAFT", hints) is Tag.BODY


def test_classify_appropriations_intermediate():
    hints = StyleHints(centered=False, all_caps=True, indent_level=2)
    assert classify("OPERATION AND MAINTENANCE", hints) is Tag.APPRO_INTERMEDIATE


def test_classify_appropriations_small_run_in():
    hints = StyleHints(bold=True, has_trailing_amount=True)
    assert (
        classify(
            "SALARIES AND EXPENSES.—For necessary expenses, $1,234,567.",
            hints,
        )
        is Tag.APPRO_SMALL
    )


def test_classify_default_body():
    hints = StyleHints(centered=False, all_caps=False, indent_level=0)
    assert classify("This is a normal paragraph of body text.", hints) is Tag.BODY


def test_classify_empty_is_body():
    assert classify("", None) is Tag.BODY
