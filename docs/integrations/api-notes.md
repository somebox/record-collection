---
title: "API probe notes"
last_updated: 2026-08-22
status: archived
scope: integrations
audience: developer
tags: [discogs, openrouter, brother-ql]
---

> Archived. These notes informed the initial implementation; verify against the live APIs before relying on endpoint details.

# API probe notes (2026-08-22)

Findings from probing the Discogs and OpenRouter APIs with the keys in `secrets.yaml`,
plus label-printer research.

## Discogs

- Auth: PAT via header `Authorization: Discogs token=<PAT>`, plus a `User-Agent`
  (Discogs requires one). Verified with `GET /oauth/identity` →
  username **outfigurable** (user id 4902585).
- Rate limit: 60 requests/min authenticated. Responses carry
  `X-Discogs-Ratelimit*` headers — the sync client must throttle and retry on 429.

### Collection

- `GET /users/{u}/collection/folders` — 13 folders found. Folder `0` = "All"
  (virtual, 268 items), folder `1` = "Uncategorized" (76). Real folders include
  jazz (54), rock/alt (68), electro/club (27), orchestral jazz (25), classical (11),
  plus several empty ones (miles davis, weather report, soundtrack, modular
  arrangements).
- `GET /users/{u}/collection/folders/{id}/releases?per_page=100` — paginated items.
  Each item has `id` (release), `instance_id` (this copy), `folder_id`, `date_added`,
  `rating`, and `basic_information` (title, year, artists, labels+catno, formats,
  genres, styles, thumb/cover image URLs, master_id).
- **`basic_information` does NOT include custom field values.** To read Notes/Style/
  Summary per item, request the folder releases with the collection items endpoint —
  field values appear in a `notes` array (`field_id` + `value`) on each instance when
  querying a specific folder as the collection owner. Verify during implementation;
  fall back to per-instance fetch if needed.

### Custom fields (`GET /users/{u}/collection/fields`)

| id | name | type |
|----|------|------|
| 1 | Media Condition | dropdown (Mint (M) … Poor (P)) |
| 2 | Sleeve Condition | dropdown (Generic, No Cover, Mint … Poor) |
| 3 | Notes | textarea |
| 4 | Summary | textarea |
| 5 | Style | textarea |

### Writes (for push-back)

- Move instance between folders:
  `POST /users/{u}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}`
  with `{"folder_id": <new>}`.
- Edit a custom field:
  `POST /users/{u}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}/fields/{field_id}`
  with `{"value": "..."}`.
- Create folder: `POST /users/{u}/collection/folders` `{"name": "..."}`;
  rename: `POST .../folders/{id}`; delete only when empty.

### Prices

- `GET /marketplace/price_suggestions/{release_id}` — suggested price per condition
  grade (requires seller settings on some accounts; verify).
- `GET /releases/{id}` includes `lowest_price` and `num_for_sale`; community stats
  give a "value" range (min/median/max) via `GET /releases/{id}/stats` on some API
  versions. "Current average price" for the UI will likely mean the **median** of
  price suggestions or release `lowest_price` — decide in implementation.
- Release detail also has `notes` (prose description), useful input for AI summaries.

### Deep links (for QR codes)

- Release: `https://www.discogs.com/release/{release_id}`
- Folder in collection: `https://www.discogs.com/user/{u}/collection?folder={folder_id}`

## OpenRouter

- Endpoint: `POST https://openrouter.ai/api/v1/chat/completions`,
  `Authorization: Bearer <key>`. Verified working.
- Model ID is literally **`~google/gemini-flash-latest`** — the tilde is part of the
  ID (an OpenRouter alias; currently resolves to `google/gemini-3.7-flash`).
- It is a reasoning model: thinking tokens count against `max_tokens`. Set a generous
  `max_tokens` (e.g. 2000+) or pass `"reasoning": {"enabled": false}` /
  `"reasoning": {"effort": "low"}` for short structured outputs, or the visible
  content comes back empty with `finish_reason: "length"`.
- Cost observed: ~$0.00001 per tiny request — summarizing all 268 albums is well
  under a cent-scale concern.
- Web search: append `:online` to the model ID or use the `plugins: [{"id": "web"}]`
  option for search-grounded requests (for Wikipedia-style album background).

## Brother QL label printer

- The printer is **not wireless**, so it is probably a **QL-700** (the USB-only
  sibling of the QL-710W) — exact model to be confirmed against the device
  (`lsusb` / `brother_ql discover`, or the sticker on the bottom). All QL-5xx/7xx
  models speak the same raster protocol; the model name is just a config value.
- Use **[`brother-ql-next`](https://pypi.org/project/brother-ql-next/)** — the
  maintained fork of [pklaus/brother_ql](https://github.com/pklaus/brother_ql)
  (original unreleased since 2019). Checked 2026-08-22: v0.12.0, released
  2026-05-20, Python ≥3.9; QL-700 and QL-710W both in the supported-model list.
- Speaks the QL raster protocol directly — **no printer driver needed**. Feed it
  a PNG; it converts and sends.
- Backend: **USB via `pyusb`** (`usb://0x04f9:...`, discoverable). On Linux a
  udev rule may be needed for non-root access; `linux_kernel` backend
  (`/dev/usb/lp0`) is a zero-dep fallback.
- Label media: 62mm continuous roll (DK-22205) fits both divider and sleeve
  labels; printable width at 300dpi ≈ 696px. Die-cut rolls (e.g. DK-11201
  29×90mm) are an option for dividers. Media type is a CLI/API parameter —
  confirm what's loaded in the printer during implementation.
- QL printers are thermal, monochrome — the black & white label design is a
  perfect match (no grayscale dithering needed if art stays pure b/w).
