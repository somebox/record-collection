# Development plan

High-level sequence. Each milestone ends in something usable.
Status: all 6 milestones done (2026-08-22). Remaining: physical print calibration,
bulk summarize/classify runs at the user's discretion.

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
