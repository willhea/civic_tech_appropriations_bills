# Staffer Tool UI Prototype

A static HTML/CSS/JS prototype of how a browser-extension version of the
bill-diff tool would feel. Built for the May 12, 2026 civic-tech demo.

This is **not** the extension. It mocks the look, navigation, and view modes
the real MV3 extension will eventually ship with. There is no upload, no
parsing, and no network beyond local `fetch()` of pre-generated sample JSONs.

## What this demonstrates

- The **canonical diff JSON v1.0** as the architectural keystone — see
  `sample-diffs/schema.md` for the prose spec and `schema.json` for the
  validator. The same JSON shape backs every renderer (HTML, Markdown, JSON,
  CSV) and every pipeline (XML, PDF).
- **Two view modes** the v1 extension will ship with:
  - *Side-by-side cards*: hunt for what changed.
  - *Tracked-changes inline*: read the bill front-to-back with marks.
- **Library rail labeled "v2 future"** — v1 is ephemeral by design (panic-user
  persona). The library is included here to show the direction without
  implying it ships in v1.
- **Mocked add-bill and export flows** so the audience sees the intended
  workflow without confusing the demo with a half-working file picker.

## Running it

From the repo root:

```sh
cd prototype
python3 -m http.server 8765
# then open http://localhost:8765/ in Chrome or Edge
```

A plain `file://` open will not work — `fetch()` of the sample JSONs needs an
HTTP origin.

## Regenerating the sample diffs

The samples in `sample-diffs/` are produced by running the existing Python
diff pipelines through `formatters.canonical`. To regenerate after changing
the canonical schema or producers:

```sh
.venv/bin/python prototype/generate_samples.py
```

Each sample is validated against `sample-diffs/schema.json` before being
written (best-effort; skipped silently if `jsonschema` isn't installed).

## File layout

```
prototype/
├── README.md                   (this file)
├── index.html                  shell + modal markup
├── styles.css
├── app.js                      vanilla JS, no dependencies
├── generate_samples.py         drives the existing pipelines into canonical JSON
└── sample-diffs/
    ├── schema.md               canonical diff JSON v1.0 prose spec
    ├── schema.json             JSON Schema (Draft 2020-12)
    ├── hr4366-reported-vs-engrossed-xml.json   real XML pair
    ├── hr4366-reported-vs-engrossed-pdf.json   real PDF pair (same bill)
    └── synthetic-edge-cases.json               renumbered/relocated/degraded
```

## What's intentionally faked

- File upload (`+ Add bill`) opens an explanatory modal instead of a real
  picker.
- Export (`Export bundle`) opens a modal listing what the production bundle
  would contain. Nothing is actually downloaded.
- The library rail is decorative within v1's strategic scope — see the
  "v2 future" badge.

## What's intentionally real

- The canonical JSON shape is the same one the real extension and the existing
  Python tool will produce.
- The renderer logic (cards, tracked-changes word marks, citation format,
  amount formatting) is meaningful work that can be lifted into the extension.
- The HR4366 XML and PDF samples are produced from real bill text by the same
  diff engines the production tool uses.
