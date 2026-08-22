# Record Collection — Spec

## Purpose

Mirror a Discogs collection locally so that the digital organization (folders) matches
the physical one (crates with dividers). Provide a web UI to browse and reorganize,
a CLI (`records`) to sync both directions, and labels (dividers + album sleeves)
printed directly on a Brother QL printer (USB) with QR codes linking back to Discogs.

## Concepts

| Concept | Discogs | Physical | App |
|---------|---------|----------|-----|
| Folder | collection folder | crate section behind a divider | sidebar entry, divider label |
| Item | collection instance (`instance_id`) | one record in a sleeve | table row, sleeve label |
| Style | custom field 5 (short descriptor list) | printed on sleeve label | editable text, AI-suggestable |
| Summary | custom field 4 (one/two sentences) | printed on sleeve label | editable text, AI-generatable |
| Notes | custom field 3 (provenance notes) | printed on sleeve label | editable text |

Discogs is the source of truth; SQLite is a synced mirror plus app-local state
(price cache, AI drafts). **No offline edit queue**: edits made in the app are
written to Discogs immediately and mirrored locally on success — if Discogs is
unreachable, the edit fails visibly. This keeps sync one-directional and simple.

## Components

### 1. Library (`lib/`)

Shared code used by both CLI and web app:

- `discogs.py` — API client: auth, throttling (60 req/min), pagination; read
  folders/items/fields; write folder moves, field edits, folder create/rename.
- `db.py` — SQLite schema + queries. Tables: `folders`, `items` (instance-keyed,
  custom fields as columns), `settings`.
- `sync.py` — full pull, Discogs → DB (268 items ≈ a handful of API calls).
  No incremental diffing; a full resync is cheap and always correct.
- `ai.py` — OpenRouter client (`~google/gemini-flash-latest`): summarize an album,
  suggest style descriptors, suggest a folder, review a folder for misfits.
- `labels.py` — render divider/sleeve labels as PNGs (Pillow) with QR codes
  (segno), sized for the 62mm roll; send to the printer via `brother_ql`.

### 2. CLI (`records`)

argparse, stdlib — no CLI framework.

- `records auth` — verify Discogs identity and OpenRouter key.
- `records sync` — full pull from Discogs.
- `records serve` — start the web app.
- `records labels --divider FOLDER | --sleeves FOLDER` — print labels.
- `records summarize [--missing]` — AI Summary/Style drafts; `--write` pushes
  accepted drafts to Discogs.
- `records classify` — AI folder suggestions (default: Uncategorized) or
  `--review FOLDER` to flag misfits.

### 3. Web app

Flask + Jinja templates, one vendored JS file (SortableJS) for drag & drop.
No build step, localhost only.

- **Collection view** — folder sidebar with counts; item table: cover thumb, title,
  artist, year, style, date added, notes, price. Sort + text filter.
- **Reorganize** — drag rows onto folders; create/rename folders. Writes go
  straight to Discogs.
- **Item detail** — edit Style/Summary/Notes/conditions; "Generate with AI" shows
  a draft the user approves before save; print-sleeve-label button; Discogs link.
- **Print labels** — pick folder + label type, preview, print.

Wireframe: see the published design canvas (docs/wireframe/).

### 4. Labels (Brother QL, USB)

- Printed via **`brother-ql-next`** (maintained fork of `brother_ql`, no driver
  needed) over **USB** (`pyusb`). The printer is not wireless — likely a QL-700;
  exact model is confirmed at setup (`records auth` reports it via discovery)
  and stored as config, since all QL models share the raster protocol.
- Labels are Pillow-rendered PNGs on 62mm continuous roll (DK-22205), pure
  black & white (thermal printers are monochrome — no grayscale, no dithering).
- **Design language**: sans-serif throughout; *italics* for descriptive text
  (summary, notes); large bold type for divider titles.
  - **Divider**: folder name in large bold caps, genre line small, QR → folder
    on Discogs.
  - **Sleeve**: title bold, artist · year regular, style line small, summary in
    italic (2–3 lines), notes in italic if present, QR → release on Discogs.
- QR codes generated locally with `segno` (zero-dep).
- The web app follows the same aesthetic: black & white, sans-serif, italic
  descriptions — the screen looks like the labels.

### 5. AI assist (OpenRouter)

- Summaries from Discogs release notes; `:online` web-search fallback when the
  release has no notes. Output constrained to short, label-friendly text.
- Style: short comma-separated descriptors ("ambient, quiet, minimalist").
- Classify: suggest a folder given the folder list + item metadata; review mode
  flags items that don't fit.
- All AI output is a draft until accepted; accepted values go to Discogs fields.

## Stack

Python 3.12+ managed with `uv`. Dependencies (deliberately few):

| dep | for |
|-----|-----|
| `httpx` | Discogs + OpenRouter APIs |
| `pyyaml` | secrets.yaml |
| `flask` | web app |
| `pillow` | label rendering |
| `brother-ql-next` | Brother QL printing |
| `pyusb` | USB backend for the printer |
| `segno` | QR codes |

stdlib: `sqlite3`, `argparse`. Frontend: Jinja + vendored SortableJS, no build.

## Cut for simplicity (revisit only if needed)

- Offline edit queue / outbox — edits require Discogs to be reachable.
- Incremental sync — full resync every time.
- Price detail — one cached price per release (Discogs `lowest_price`), fetched
  lazily and refreshable; no per-condition price suggestions.
- Browser/HTML label printing — the QL-710W path replaces it.
- Multi-user, auth, deployment — localhost only.
- Sync conflict detection — Discogs wins, always.
