"""SQLite mirror of the Discogs collection."""

import sqlite3

from lib.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    color TEXT  -- app-local override; NULL = auto pastel
);

CREATE TABLE IF NOT EXISTS items (
    instance_id INTEGER PRIMARY KEY,
    release_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL REFERENCES folders(id),
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    year INTEGER,
    date_added TEXT,
    thumb_url TEXT,
    cover_url TEXT,
    label TEXT,
    catno TEXT,
    genres TEXT,        -- comma-joined, from Discogs release data
    discogs_styles TEXT, -- comma-joined, from Discogs release data
    style TEXT,          -- custom field 5: short descriptors for the label
    summary TEXT,        -- custom field 4
    notes TEXT,          -- custom field 3
    media_condition TEXT,  -- custom field 1
    sleeve_condition TEXT  -- custom field 2
);
CREATE INDEX IF NOT EXISTS idx_items_folder ON items(folder_id);

-- App-local price cache; survives collection resyncs.
CREATE TABLE IF NOT EXISTS prices (
    release_id INTEGER PRIMARY KEY,
    price REAL,
    num_for_sale INTEGER,
    fetched_at TEXT NOT NULL
);

-- App-local: what the user actually paid. Not a Discogs concept; survives resyncs.
CREATE TABLE IF NOT EXISTS purchases (
    instance_id INTEGER PRIMARY KEY,
    paid_price REAL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(folders)")]
    if "color" not in cols:
        with conn:
            conn.execute("ALTER TABLE folders ADD COLUMN color TEXT")
    return conn


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
