"""Full pull: Discogs -> SQLite. Discogs is the source of truth, so the mirror
tables are rebuilt wholesale; the price cache is keyed by release and survives."""

import re
import sqlite3
from datetime import datetime, timezone

from lib.db import set_setting
from lib.discogs import DiscogsClient

# Custom collection field ids, confirmed via /collection/fields (docs/api-notes.md).
FIELD_MEDIA = 1
FIELD_SLEEVE = 2
FIELD_NOTES = 3
FIELD_SUMMARY = 4
FIELD_STYLE = 5


def _artist_names(artists: list[dict]) -> str:
    names = []
    for a in artists:
        name = a.get("anv") or a["name"]
        names.append(re.sub(r" \(\d+\)$", "", name))  # drop Discogs disambiguation suffix
    return ", ".join(names)


def _field_values(item: dict) -> dict[int, str]:
    return {n["field_id"]: n["value"] for n in item.get("notes", [])}


def pull(discogs: DiscogsClient, conn: sqlite3.Connection, username: str) -> dict:
    folders = discogs.folders(username)
    items = list(discogs.collection_items(username, folder_id=0))

    colors = {
        r["id"]: r["color"]
        for r in conn.execute("SELECT id, color FROM folders WHERE color IS NOT NULL")
    }
    with conn:
        conn.execute("DELETE FROM items")
        conn.execute("DELETE FROM folders")
        for f in folders:
            if f["id"] == 0:
                continue  # virtual "All" folder
            conn.execute(
                "INSERT INTO folders (id, name, count, color) VALUES (?, ?, ?, ?)",
                (f["id"], f["name"], f["count"], colors.get(f["id"])),
            )
        for item in items:
            info = item["basic_information"]
            fields = _field_values(item)
            first_label = (info.get("labels") or [{}])[0]
            conn.execute(
                """INSERT INTO items (instance_id, release_id, folder_id, title, artist,
                       year, date_added, thumb_url, cover_url, label, catno, genres,
                       discogs_styles, style, summary, notes, media_condition, sleeve_condition)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["instance_id"],
                    info["id"],
                    item["folder_id"],
                    info["title"],
                    _artist_names(info.get("artists", [])),
                    info.get("year") or None,
                    item.get("date_added"),
                    info.get("thumb"),
                    info.get("cover_image"),
                    first_label.get("name"),
                    first_label.get("catno"),
                    ", ".join(info.get("genres", [])),
                    ", ".join(info.get("styles", [])),
                    fields.get(FIELD_STYLE),
                    fields.get(FIELD_SUMMARY),
                    fields.get(FIELD_NOTES),
                    fields.get(FIELD_MEDIA),
                    fields.get(FIELD_SLEEVE),
                ),
            )
        set_setting(conn, "username", username)
        set_setting(conn, "last_sync", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    return {"folders": len(folders) - 1, "items": len(items)}
