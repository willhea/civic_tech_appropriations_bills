"""Tests for formatters.canonical: pipeline-neutral diff JSON.

Two producer functions:
  xml_diff_to_canonical(diff_dict)        -> dict
  pdf_diff_to_canonical(pdf_diff, **meta) -> dict

One consumer:
  view_from_canonical(canonical)          -> DiffView

The producers are tested against the canonical JSON shape directly. The
consumer is tested for round-trip parity against the existing
xml_dict_to_view / pdf_diff_to_view adapters, so the existing HTML
renderer keeps working unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from formatters.canonical import (
    pdf_diff_to_canonical,
    view_from_canonical,
    xml_diff_to_canonical,
)

from diff_pdf import PdfDiff, PdfHunk
from formatters.adapters import pdf_diff_to_view, xml_dict_to_view
from parsers.pdf_anchors import Anchor

SCHEMA_VERSION = "1.0"


# ---------- XML producer ------------------------------------------------------


def _xml_diff_dict(*, changes=None, **overrides) -> dict:
    base = {
        "bill_type": "hr",
        "bill_number": 4366,
        "congress": 118,
        "old_version": "Reported in House",
        "new_version": "Engrossed in House",
        "old_version_number": 1,
        "new_version_number": 2,
        "summary": {"added": 1, "removed": 0, "modified": 2, "moved": 0},
        "changes": changes or [],
    }
    base.update(overrides)
    return base


def test_xml_envelope_has_versioned_metadata():
    canonical = xml_diff_to_canonical(_xml_diff_dict())
    assert canonical["schema_version"] == SCHEMA_VERSION
    assert canonical["bill"] == {"type": "hr", "number": 4366, "congress": 118}
    assert canonical["versions"]["v1"] == {
        "label": "Reported in House",
        "version_number": 1,
        "source": "xml",
    }
    assert canonical["versions"]["v2"] == {
        "label": "Engrossed in House",
        "version_number": 2,
        "source": "xml",
    }
    assert canonical["summary"] == {"added": 1, "removed": 0, "modified": 2, "moved": 0}
    assert canonical["changes"] == []


def test_xml_modified_change_canonical_fields():
    change = {
        "change_type": "modified",
        "display_path_old": ["TITLE I", "Customs"],
        "display_path_new": ["TITLE I", "Customs"],
        "section_number": "101",
        "old_text": "old prose",
        "new_text": "new prose",
    }
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=[change]))
    c = canonical["changes"][0]
    assert c["id"] == "c-0001"
    assert c["change_type"] == "modified"
    assert c["section_number"] == "101"
    assert c["path"] == {"v1": ["TITLE I", "Customs"], "v2": ["TITLE I", "Customs"]}
    assert c["location"] is None
    assert c["anchor_resolution"] == "resolved"
    assert c["text"] == {"old": "old prose", "new": "new prose"}
    assert c["amounts"] == []
    assert c["move"] is None


def test_xml_added_change_has_v1_null():
    change = {
        "change_type": "added",
        "display_path_old": None,
        "display_path_new": ["TITLE II", "New Section"],
        "old_text": None,
        "new_text": "new appropriation",
        "section_number": "",
    }
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=[change]))
    c = canonical["changes"][0]
    assert c["change_type"] == "added"
    assert c["path"] == {"v1": None, "v2": ["TITLE II", "New Section"]}
    assert c["text"] == {"old": None, "new": "new appropriation"}
    assert c["section_number"] == ""


def test_xml_removed_change_has_v2_null():
    change = {
        "change_type": "removed",
        "display_path_old": ["TITLE III", "Removed"],
        "display_path_new": None,
        "old_text": "deprecated",
        "new_text": None,
        "section_number": "",
    }
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=[change]))
    c = canonical["changes"][0]
    assert c["path"] == {"v1": ["TITLE III", "Removed"], "v2": None}
    assert c["text"] == {"old": "deprecated", "new": None}


def test_xml_moved_change_emits_relocated_move():
    change = {
        "change_type": "moved",
        "display_path_old": ["OLD", "Loc"],
        "display_path_new": ["NEW", "Loc"],
        "old_text": "same body",
        "new_text": "same body",
        "section_number": "",
    }
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=[change]))
    c = canonical["changes"][0]
    assert c["change_type"] == "moved"
    assert c["move"] == {"kind": "relocated", "body_unchanged": True}


def test_xml_amounts_filtered_to_real_changes():
    change = {
        "change_type": "modified",
        "display_path_old": ["X"],
        "display_path_new": ["X"],
        "old_text": "a",
        "new_text": "b",
        "section_number": "",
        "financial": {
            "paired_amounts": [(1000, 1500), (2000, 2000), (5000, None), (None, 500)],
        },
    }
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=[change]))
    assert canonical["changes"][0]["amounts"] == [{"old": 1000, "new": 1500}]


def test_xml_unchanged_changes_are_dropped():
    changes = [
        {
            "change_type": "unchanged",
            "display_path_old": ["A"],
            "display_path_new": ["A"],
            "old_text": "x",
            "new_text": "x",
            "section_number": "",
        },
        {
            "change_type": "modified",
            "display_path_old": ["B"],
            "display_path_new": ["B"],
            "old_text": "x",
            "new_text": "y",
            "section_number": "",
        },
    ]
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=changes))
    assert len(canonical["changes"]) == 1
    assert canonical["changes"][0]["change_type"] == "modified"


def test_xml_change_ids_are_stable_within_document():
    changes = [
        {
            "change_type": "modified",
            "display_path_old": ["A"],
            "display_path_new": ["A"],
            "old_text": "a",
            "new_text": "b",
            "section_number": "",
        },
        {
            "change_type": "added",
            "display_path_old": None,
            "display_path_new": ["B"],
            "old_text": None,
            "new_text": "x",
            "section_number": "",
        },
        {
            "change_type": "removed",
            "display_path_old": ["C"],
            "display_path_new": None,
            "old_text": "y",
            "new_text": None,
            "section_number": "",
        },
    ]
    canonical = xml_diff_to_canonical(_xml_diff_dict(changes=changes))
    ids = [c["id"] for c in canonical["changes"]]
    assert ids == ["c-0001", "c-0002", "c-0003"]


# ---------- PDF producer ------------------------------------------------------

TITLE_I = Anchor(page_number=1, line_number=1, kind="title", text="TITLE I")
SEC_101 = Anchor(page_number=1, line_number=10, kind="section", text="SEC. 101")
SEC_201 = Anchor(page_number=5, line_number=1, kind="section", text="SEC. 201")


def _pdf_meta() -> dict:
    return dict(bill_type="hr", bill_number=4366, congress=118, v1_label="Reported", v2_label="Engrossed")


def test_pdf_envelope_marks_source_pdf_and_version_number_null():
    diff = PdfDiff(hunks=(), v1_anchors=(), v2_anchors=())
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    assert canonical["schema_version"] == SCHEMA_VERSION
    assert canonical["versions"]["v1"]["source"] == "pdf"
    assert canonical["versions"]["v1"]["version_number"] is None
    assert canonical["versions"]["v2"]["source"] == "pdf"
    assert canonical["versions"]["v2"]["version_number"] is None
    assert canonical["bill"] == {"type": "hr", "number": 4366, "congress": 118}


def test_pdf_modified_hunk_canonical_fields():
    hunk = PdfHunk(
        change_type="modified",
        v1_anchor=SEC_101,
        v2_anchor=SEC_101,
        v1_range=(1, 10, 1, 20),
        v2_range=(2, 5, 2, 8),
        v1_text="old",
        v2_text="new",
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(TITLE_I, SEC_101), v2_anchors=(TITLE_I, SEC_101))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    c = canonical["changes"][0]
    assert c["change_type"] == "modified"
    assert c["path"] == {"v1": ["TITLE I", "SEC. 101"], "v2": ["TITLE I", "SEC. 101"]}
    assert c["location"] == {
        "v1": {"start_page": 1, "start_line": 10, "end_page": 1, "end_line": 20},
        "v2": {"start_page": 2, "start_line": 5, "end_page": 2, "end_line": 8},
    }
    assert c["anchor_resolution"] == "resolved"
    assert c["text"] == {"old": "old", "new": "new"}
    assert c["section_number"] == ""


def test_pdf_unnumbered_line_becomes_null():
    hunk = PdfHunk(
        change_type="modified",
        v1_anchor=SEC_101,
        v2_anchor=SEC_101,
        v1_range=(1, -1, 1, -1),
        v2_range=(2, 5, 2, 8),
        v1_text="x",
        v2_text="y",
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(SEC_101,), v2_anchors=(SEC_101,))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    loc = canonical["changes"][0]["location"]
    assert loc["v1"] == {"start_page": 1, "start_line": None, "end_page": 1, "end_line": None}
    assert loc["v2"]["start_line"] == 5


def test_pdf_added_hunk_has_v1_path_and_location_null():
    hunk = PdfHunk(
        change_type="added",
        v1_anchor=None,
        v2_anchor=SEC_101,
        v1_range=None,
        v2_range=(1, 10, 1, 20),
        v1_text="",
        v2_text="brand new",
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(), v2_anchors=(SEC_101,))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    c = canonical["changes"][0]
    assert c["path"]["v1"] is None
    assert c["path"]["v2"] == ["SEC. 101"]
    assert c["location"]["v1"] is None
    assert c["location"]["v2"] is not None
    assert c["text"]["old"] is None
    assert c["text"]["new"] == "brand new"


def test_pdf_degraded_hunk_marks_anchor_resolution_and_nulls_paths():
    hunk = PdfHunk(
        change_type="modified",
        v1_anchor=None,
        v2_anchor=None,
        v1_range=(2, 5, 2, 8),
        v2_range=(2, 5, 2, 8),
        v1_text="x",
        v2_text="y",
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(), v2_anchors=())
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    c = canonical["changes"][0]
    assert c["anchor_resolution"] == "degraded"
    assert c["path"] == {"v1": None, "v2": None}
    # Location is still present — that's the renderer's fallback.
    assert c["location"]["v1"]["start_page"] == 2


def test_pdf_renumbered_move_emits_kind_and_labels():
    hunk = PdfHunk(
        change_type="moved",
        v1_anchor=SEC_101,
        v2_anchor=SEC_201,
        v1_range=(1, 10, 1, 20),
        v2_range=(5, 1, 5, 12),
        v1_text="same body",
        v2_text="same body",
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(SEC_101,), v2_anchors=(SEC_201,))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    move = canonical["changes"][0]["move"]
    assert move == {
        "kind": "renumbered",
        "old_label": "SEC. 101",
        "new_label": "SEC. 201",
        "body_unchanged": True,
    }


def test_pdf_relocated_move_when_anchor_text_unchanged():
    """Same anchor text on both sides but the page changed -- relocated, not renumbered."""
    hunk = PdfHunk(
        change_type="moved",
        v1_anchor=SEC_101,
        v2_anchor=SEC_101,
        v1_range=(1, 10, 1, 20),
        v2_range=(8, 1, 8, 12),
        v1_text="same body",
        v2_text="same body",
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(SEC_101,), v2_anchors=(SEC_101,))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    assert canonical["changes"][0]["move"] == {"kind": "relocated", "body_unchanged": True}


def test_pdf_amounts_filtered_to_real_changes():
    hunk = PdfHunk(
        change_type="modified",
        v1_anchor=SEC_101,
        v2_anchor=SEC_101,
        v1_range=(1, 1, 1, 5),
        v2_range=(1, 1, 1, 5),
        v1_text="x",
        v2_text="y",
        amount_pairs=((1000, 1500), (2000, 2000), (None, 500), (5000, None)),
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(SEC_101,), v2_anchors=(SEC_101,))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    assert canonical["changes"][0]["amounts"] == [{"old": 1000, "new": 1500}]


# ---------- Round-trip parity ------------------------------------------------


def test_xml_round_trip_preserves_view_for_renderer():
    """xml_diff_to_canonical -> view_from_canonical reproduces the same DiffView
    that xml_dict_to_view would produce directly. This means the existing HTML
    renderer keeps working unchanged when fed canonical JSON."""
    diff_dict = _xml_diff_dict(
        changes=[
            {
                "change_type": "modified",
                "display_path_old": ["TITLE I", "Customs"],
                "display_path_new": ["TITLE I", "Customs"],
                "section_number": "101",
                "old_text": "old",
                "new_text": "new",
                "financial": {"paired_amounts": [(1000, 1500)]},
            },
            {
                "change_type": "moved",
                "display_path_old": ["OLD"],
                "display_path_new": ["NEW"],
                "old_text": "same",
                "new_text": "same",
                "section_number": "",
            },
        ]
    )
    direct = xml_dict_to_view(diff_dict)
    via_canonical = view_from_canonical(xml_diff_to_canonical(diff_dict))
    assert via_canonical == direct


def test_pdf_round_trip_preserves_view_for_renderer():
    hunks = (
        PdfHunk("modified", SEC_101, SEC_101, (1, 10, 1, 20), (2, 5, 2, 8), "old", "new"),
        PdfHunk("moved", SEC_101, SEC_201, (1, 10, 1, 20), (5, 1, 5, 12), "same body", "same body"),
        PdfHunk("modified", None, None, (3, 1, 3, 4), (3, 1, 3, 4), "x", "y"),
    )
    diff = PdfDiff(hunks=hunks, v1_anchors=(TITLE_I, SEC_101), v2_anchors=(TITLE_I, SEC_201))
    direct = pdf_diff_to_view(diff, **_pdf_meta())
    via_canonical = view_from_canonical(pdf_diff_to_canonical(diff, **_pdf_meta()))
    assert via_canonical == direct


# ---------- Schema validation -------------------------------------------------


def _load_schema() -> dict:
    return json.loads(Path("prototype/sample-diffs/schema.json").read_text())


def test_xml_canonical_validates_against_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    diff_dict = _xml_diff_dict(
        changes=[
            {
                "change_type": "modified",
                "display_path_old": ["A"],
                "display_path_new": ["A"],
                "old_text": "x",
                "new_text": "y",
                "section_number": "",
                "financial": {"paired_amounts": [(100, 200)]},
            },
            {
                "change_type": "added",
                "display_path_old": None,
                "display_path_new": ["B"],
                "old_text": None,
                "new_text": "z",
                "section_number": "",
            },
            {
                "change_type": "moved",
                "display_path_old": ["C"],
                "display_path_new": ["D"],
                "old_text": "s",
                "new_text": "s",
                "section_number": "",
            },
        ]
    )
    canonical = xml_diff_to_canonical(diff_dict)
    jsonschema.validate(canonical, _load_schema())


def test_pdf_canonical_validates_against_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    hunks = (
        PdfHunk("modified", SEC_101, SEC_101, (1, 10, 1, 20), (2, 5, 2, 8), "x", "y", amount_pairs=((100, 200),)),
        PdfHunk("moved", SEC_101, SEC_201, (1, 10, 1, 20), (5, 1, 5, 12), "same", "same"),
        PdfHunk("modified", None, None, (3, 1, 3, 4), (3, 1, 3, 4), "a", "b"),
        PdfHunk("added", None, SEC_201, None, (5, 1, 5, 12), "", "new"),
    )
    diff = PdfDiff(hunks=hunks, v1_anchors=(SEC_101,), v2_anchors=(SEC_101, SEC_201))
    canonical = pdf_diff_to_canonical(diff, **_pdf_meta())
    jsonschema.validate(canonical, _load_schema())
