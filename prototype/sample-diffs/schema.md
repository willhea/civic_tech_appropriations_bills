# Canonical Diff JSON — v1.0

This document specifies the canonical JSON shape produced when comparing two
versions of a bill. It is the public contract between the diff engine and any
consumer (HTML/Markdown/CSV renderers, the staffer browser extension, future
dashboards, third-party tooling). It is pipeline-neutral: a diff produced from
XML inputs and a diff produced from PDF inputs share this shape.

## Versioning

Top-level field: `schema_version: "1.0"`.

- Consumers SHOULD reject documents whose major version they do not understand.
- Additive, backward-compatible changes (new optional fields) bump the minor:
  `1.0 → 1.1`.
- Breaking changes (renamed/removed/restructured fields) bump the major:
  `1.0 → 2.0`. N-way comparison support is planned as a v2.0 break.

## Scope

- **Binary only.** v1.0 represents a single comparison of two bill versions
  (`v1` and `v2`). N-way comparison is out of scope and will be a v2.0 break.
- **Read-only diff data.** No edit instructions, comments, or annotations.
- **Semantic, not presentational.** The JSON does not carry pre-rendered
  HTML; renderers are pure functions over this shape.

## Top-level shape

```jsonc
{
  "schema_version": "1.0",
  "generator": { "name": "appropriations_bills", "version": "0.x" },
  "bill":      { "type": "HR", "number": 4366, "congress": 118 },
  "versions": {
    "v1": { "label": "Engrossed in House", "version_number": 1,    "source": "xml" },
    "v2": { "label": "Public Law",         "version_number": 4,    "source": "xml" }
  },
  "summary":  { "added": 12, "removed": 8, "modified": 47, "moved": 3 },
  "changes":  [ /* ChangeObject, see below */ ]
}
```

### `bill`

| Field      | Type              | Notes                                                       |
|------------|-------------------|-------------------------------------------------------------|
| `type`     | string            | Bill type code, e.g., `"HR"`, `"S"`, `"HJRES"`. May be empty. |
| `number`   | integer \| string | Integer for canonical bills (e.g., `4366`); string for drafts or non-numeric identifiers. |
| `congress` | integer \| string | Congress number, e.g., `118`. May be empty string when unknown. |

### `versions.v1` and `versions.v2`

| Field            | Type                | Notes                                                                                       |
|------------------|---------------------|---------------------------------------------------------------------------------------------|
| `label`          | string              | Human-readable label, e.g., `"Engrossed in House"`, `"Public Law"`, `"draft"`.              |
| `version_number` | integer \| null     | Ordinal index when known (XML pipeline). `null` for PDFs.                                   |
| `source`         | `"xml"` \| `"pdf"`  | Provenance. Lets consumers reason about structural confidence.                              |

### `summary`

Object with integer counts keyed by `change_type`. Keys with zero count MAY be
omitted. The four canonical keys are `added`, `removed`, `modified`, `moved`.

### `changes`

Ordered array of ChangeObjects. Order is the renderer's display order; consumers
that need a different order MUST resort.

## ChangeObject

```jsonc
{
  "id": "c-0001",
  "change_type": "modified",
  "section_number": "101",
  "path": {
    "v1": ["Title I", "Department of X", "Sec. 101"],
    "v2": ["Title I", "Department of X", "Sec. 101"]
  },
  "location": {
    "v1": { "start_page": 12, "start_line": 4,    "end_page": 12, "end_line": 18 },
    "v2": { "start_page": 13, "start_line": null, "end_page": 13, "end_line": null }
  },
  "anchor_resolution": "resolved",
  "text":    { "old": "...", "new": "..." },
  "amounts": [ { "old": 5000000, "new": 5500000 } ],
  "move":    null
}
```

### `id`

String, unique within a single document. Format `c-NNNN` recommended.

**Stability**: stable within one generation (consumers can use it as a UI
selection key during a session). NOT stable across regenerations of the same
diff — IDs may renumber if inputs change. Consumers needing cross-run
stability MUST compute their own keys from semantic fields.

### `change_type`

String enum: `"added"` | `"removed"` | `"modified"` | `"moved"`.

### `section_number`

String. Extracted from `path` for renderer convenience; renderers may use it
for distinct styling. `""` or `null` when not applicable. **Redundant with
`path`** but retained because the HTML renderer styles it as a separate prefix.

### `path`

Breadcrumb arrays per side. Each element is one segment of the bill's
hierarchical structure (Title → Subtitle → Section → ...).

| Side | When `null`                                         |
|------|-----------------------------------------------------|
| `v1` | Pure additions (`change_type: "added"`).            |
| `v2` | Pure removals (`change_type: "removed"`).           |

For `change_type: "moved"`, both sides are present and may differ.

For PDF diffs where neither anchor resolved, both sides are `null` and
`anchor_resolution` is `"degraded"`.

Renderers MUST escape segments individually before joining (a literal `>` in a
segment must not collide with a `>` separator).

### `location`

Page+line citations. Always `null` for XML diffs (XML carries no source
coordinates). For PDF diffs:

```jsonc
"location": {
  "v1": { "start_page": int, "start_line": int|null, "end_page": int, "end_line": int|null } | null,
  "v2": { ... }                                                                              | null
}
```

| Field                       | Notes                                                                |
|-----------------------------|----------------------------------------------------------------------|
| `start_page` / `end_page`   | 1-indexed page number.                                               |
| `start_line` / `end_line`   | 1-indexed line number, or `null` when the source is unnumbered.     |

A whole side (`location.v1` or `location.v2`) is `null` when that side is absent
(`added` has `v1: null`; `removed` has `v2: null`).

### `anchor_resolution`

String enum: `"resolved"` | `"degraded"`.

- `"resolved"` — at least one side's path was resolved successfully. Always
  `"resolved"` for XML diffs.
- `"degraded"` — PDF anchor detection failed on both sides; `path` is `null`
  on both sides. Renderers should fall back to a `location`-based label.

Future minor versions MAY introduce `"partial"` (one side resolved, one not).

### `text`

```jsonc
"text": { "old": string|null, "new": string|null }
```

Plain text bodies. `null` on the side that doesn't exist (`added`: `old=null`;
`removed`: `new=null`). Word-level inline diffs are NOT carried in the JSON;
renderers compute them at render time.

### `amounts`

Pre-filtered list of `(old, new)` integer pairs representing meaningful base
amount changes. Filter rule (guaranteed by the producer):

- Both `old` and `new` are present (non-null).
- `old != new`.

Pairs where one side is `null` (pure annotation insertions) and pairs where
old equals new are dropped before serialization. Consumers needing the
unfiltered set must wait for a future field; v1.0 does not expose it.

```jsonc
"amounts": [ { "old": 5000000, "new": 5500000 }, ... ]
```

### `move`

Object when `change_type == "moved"`, `null` otherwise.

```jsonc
"move": {
  "kind": "renumbered" | "relocated",
  "old_label": string,   // present iff kind == "renumbered"
  "new_label": string,   // present iff kind == "renumbered"
  "body_unchanged": boolean
}
```

- `"renumbered"` — the section's anchor identifier changed (e.g., `"Sec. 401"`
  became `"Sec. 501"`). `old_label` and `new_label` carry the anchor texts.
- `"relocated"` — the section moved within the bill's hierarchy without an
  identifier change. Use the `path` arrays to describe the move; labels are
  omitted.
- `body_unchanged` — `true` when `text.old == text.new`. Renderers may use
  this to suppress redundant body display on pure renumber/relocate moves.

## Field omission policy

The producer SHOULD emit all fields documented above on every change object,
using `null` for absent values. Consumers SHOULD treat missing optional fields
the same as `null`. This keeps the JSON predictable for schema validation
while leaving room for additive fields in minor versions.

## Out of scope for v1.0

- N-way comparison (more than two versions in a single document)
- Cross-reference pairing (mapping an `"added"` change to a related
  `"removed"` change)
- Source file hashes or signatures
- Inline word-level diff annotations
- AI-generated summaries, importance scores, or annotations

These may appear in future minor versions (additive) or v2.0 (breaking).
