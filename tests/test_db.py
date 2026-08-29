"""Tests for lib.db: connect(), PRAGMA foreign_keys, and schema helpers."""

import logging
import sqlite3

import pytest

from lib import db


def test_connect_enables_foreign_keys_when_no_orphans(conn):
    """A fresh DB with no orphan rows should have FK enforcement on."""
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1, "PRAGMA foreign_keys should be ON after db.connect()"


def test_valid_folder_item_insert_succeeds(conn):
    """Sanity: with FK on, a valid folder/item pair inserts cleanly."""
    with conn:
        conn.execute("INSERT INTO folders (id, name, count) VALUES (1, 'jazz', 1)")
        conn.execute(
            """INSERT INTO items (instance_id, release_id, folder_id, title, artist)
               VALUES (1, 100, 1, 'Kind Of Blue', 'Miles Davis')"""
        )
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1


def test_orphan_insert_is_rejected(conn):
    """With FK enforcement on, inserting an item with a non-existent
    folder_id must be rejected with ``IntegrityError``."""
    with conn:
        conn.execute("INSERT INTO folders (id, name, count) VALUES (1, 'jazz', 0)")
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                """INSERT INTO items (instance_id, release_id, folder_id,
                       title, artist) VALUES (1, 100, 9999, 'x', 'y')"""
            )


def test_pragma_skipped_when_orphans_exist(tmp_path, monkeypatch, caplog):
    """If the DB has pre-existing orphan rows, ``connect()`` must NOT
    enable FK and must log a warning explaining why.

    Strategy: build a clean DB with FK on, then open a side connection
    (FK defaults to OFF on new connections) and inject an orphan row.
    Reconnect via ``db.connect()`` and assert it detects the orphan.
    """
    path = tmp_path / "orphan.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", path)

    # 1. First connect: clean DB — FK should be enabled.
    conn1 = db.connect()
    with conn1:
        conn1.execute("INSERT INTO folders (id, name, count) VALUES (1, 'a', 0)")
        conn1.execute(
            """INSERT INTO items (instance_id, release_id, folder_id,
                   title, artist) VALUES (1, 1, 1, 't', 'a')"""
        )
    conn1.close()

    # 2. Inject an orphan via a side connection (FK is off by default
    #    on a brand-new sqlite3 connection, so the bad row is accepted).
    raw = sqlite3.connect(path)
    raw.execute(
        """INSERT INTO items (instance_id, release_id, folder_id,
               title, artist) VALUES (42, 1, 9999, 'orphan', 'x')"""
    )
    raw.commit()
    raw.close()

    # 3. Reconnect via db.connect — should detect the orphan, log a
    #    warning, and leave FK off.
    caplog.set_level(logging.WARNING, logger="lib.db")
    conn2 = db.connect()
    try:
        fk = conn2.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 0, "PRAGMA foreign_keys must remain OFF when orphans exist"
        warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "skipping PRAGMA foreign_keys" in r.message
        ]
        assert warnings, "expected a warning explaining the skip"
        assert "1 orphan" in warnings[0].message
    finally:
        conn2.close()
