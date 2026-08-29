---
title: "Development plan"
last_updated: 2026-08-22
status: current
scope: operations
audience: maintainer
tags: [plan, milestones, history]
---

# Development plan

High-level sequence. Each milestone ends in something usable.
Status: all 6 milestones done (2026-08-22). Since then: collection fully enriched
(268/268 Style+Summary), Uncategorized filed, rock split into subgenres, artist
sections created, folder colors, paid prices, multi-select bulk actions, modal
detail UX, variable-height labels, CSS baseline + styleguide. Published at
github.com/somebox/record-collection.

## What's left

Blocked on hardware (the printer has not been connected yet):
- Confirm the model via USB discovery (`records auth`) — likely QL-700; may need
  a udev rule for non-root USB access on Linux.
- First real prints: check 62mm sizing, margins, contrast, QR scan distance;
  calibrate `SLEEVE_MIN/MAX_HEIGHT` and font sizes against the physical roll.
- Then the big print run: dividers for every folder + 268 sleeve labels.

Small operational items:
- 1 record still Uncategorized (Charles Aznavour — no fitting folder).

Accepted quality gaps (see docs/frontend-styleguide.md):
- No modal focus trap; table rows not keyboard-focusable; no mobile layout.

Done since: `--divider all` batch printing, PDF label output + settings.yaml,
`records backup`/`restore` for app-local data, OpenRouter made optional,
pytest suite (labels, sync, web API).

Deliberately cut (revisit only if needed): offline edit queue, incremental sync,
per-condition price suggestions, browser label printing, multi-user/auth.

## 1. Foundation ✓
- `uv` project scaffold, `pyproject.toml`, config loading (`secrets.yaml`).
- Discogs client with throttling + pagination; OpenRouter client.
- `records auth` verifying both keys end to end.

## 2. Sync ✓
- SQLite schema; `records sync` doing a full pull of folders, items, custom
  field values (Style/Summary/Notes/conditions), cover thumb URLs.
- Confirm field values land correctly for all 268 items.

## 3. Web app (read-only) ✓
- Flask app: folder sidebar, item table, sort/filter, item detail page.
- Lazy price fetch (`lowest_price`) with cache, shown in the table.

## 4. Editing ✓
- Drag & drop moves, folder create/rename, field edits on the item page —
  each writing straight to Discogs, mirroring locally on success.

## 5. Labels ✓ (rendering + endpoints tested; actual print awaits the physical printer)
- Pillow renderers for divider + sleeve labels (62mm, pure b/w, sans-serif,
  italic descriptions, big bold divider titles), segno QR codes.
- Print via `brother-ql-next` over USB — first step: discover the actual
  printer model (`brother_ql discover` / `lsusb`) and store it in config.
- `records labels` + print buttons in the web app. Calibrate against the
  real roll.

## 6. AI assist ✓
- `records summarize`: Summary + Style drafts, approve/write flow (CLI + web).
- `records classify`: folder suggestions for Uncategorized (76 items!) and
  `--review` mode.

Rough order of value: 1–3 give a browsable mirror; 4 makes it the organizing
tool; 5 delivers the physical payoff; 6 automates the tedious part.
