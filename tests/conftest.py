import pytest

from lib import db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """A fresh database in a temp dir, wired into both db and the web app."""
    path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = db.connect()
    yield conn
    conn.close()


@pytest.fixture
def seeded(conn):
    with conn:
        conn.execute("INSERT INTO folders (id, name, count) VALUES (1, 'Uncategorized', 0)")
        conn.execute("INSERT INTO folders (id, name, count, color) VALUES (10, 'jazz', 1, '#d0e6f2')")
        conn.execute("INSERT INTO folders (id, name, count) VALUES (20, 'rock', 0)")
        conn.execute(
            """INSERT INTO items (instance_id, release_id, folder_id, title, artist, year,
                   date_added, genres, discogs_styles, style, summary, notes)
               VALUES (100, 555, 10, 'Kind Of Blue', 'Miles Davis', 1959,
                   '2017-09-23T19:31:36-07:00', 'Jazz', 'Modal',
                   'modal jazz, cool', 'The classic.', 'gift')"""
        )
        conn.execute("INSERT INTO settings (key, value) VALUES ('username', 'tester')")
    return conn


@pytest.fixture
def client(seeded):
    from lib import web

    web.app.config["TESTING"] = True
    with web.app.test_client() as client:
        yield client
