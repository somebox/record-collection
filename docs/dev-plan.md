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
- No way to batch-print all dividers in one command (`--divider` is per folder).

Accepted quality gaps (see docs/styleguide.md):
- No modal focus trap; table rows not keyboard-focusable; no mobile layout.
- No tests (sync edge cases — moves/removals/field changes — are untested).
- App-local data (paid prices, folder colors) lives only in records.sqlite3 —
  no export/backup command.

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
