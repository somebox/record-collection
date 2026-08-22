# Record Collection

Organize a physical record collection using [Discogs](https://www.discogs.com) as the
source of truth. Each Discogs folder maps to a labeled section (divider) in a physical
crate; each album gets a printed sleeve label. A CLI syncs the collection into a local
SQLite database, and a small web app lets you browse, reorganize, and print labels.

## Features

- **Sync** — `records sync` pulls collection, folders, and custom fields (Style,
  Summary, Notes, conditions) from Discogs into SQLite; edits in the app write
  straight back to Discogs.
- **Web app** — table view of the collection with folders in a sidebar, drag & drop to
  move items between folders, create/rename folders, see date added, notes, and price.
- **Labels** — divider labels (title/genre) and album sleeve labels (title, artist,
  year, style, summary, notes), each with a QR code linking to the item or folder on
  Discogs — printed directly on a Brother QL label printer via USB (62mm roll,
  no driver needed). Black & white, sans-serif, italic descriptions, big bold
  divider titles.
- **AI assist** — via OpenRouter (`~google/gemini-flash-latest`): generate album
  summaries from Discogs data or the web, suggest a folder for unfiled albums,
  and review folders for misfiled items.

## Setup

```sh
cp secrets.example.yaml secrets.yaml   # then fill in real keys
uv sync
```

## Usage

```sh
uv run records auth      # verify Discogs + OpenRouter keys, find the printer
uv run records sync      # pull the collection into records.sqlite3
uv run records serve     # web app at http://127.0.0.1:5033

uv run records labels --divider jazz            # print a divider label
uv run records labels --sleeves jazz --out /tmp # export sleeve labels as PNGs

uv run records summarize --missing --limit 10   # AI-draft Style/Summary (dry run)
uv run records summarize --missing --write      # …and save to Discogs
uv run records classify                         # suggest folders for Uncategorized
uv run records classify --review jazz           # flag possible misfits in a folder
```

`secrets.yaml` needs:

- `discogs_pat` — a Discogs [personal access token](https://www.discogs.com/settings/developers)
- `openrouter_key` — an [OpenRouter](https://openrouter.ai/keys) API key

## Docs

- [docs/spec.md](docs/spec.md) — features and components
- [docs/dev-plan.md](docs/dev-plan.md) — development plan
- [docs/api-notes.md](docs/api-notes.md) — Discogs / OpenRouter / printer findings
- [docs/wireframe/](docs/wireframe/) — web app wireframe (design canvas)
