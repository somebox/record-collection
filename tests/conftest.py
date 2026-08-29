import pytest

from lib import db


class FakeDiscogs:
    """In-memory Discogs stand-in for write-path tests.

    Implements the methods that the web layer's write endpoints actually
    call: ``create_folder``, ``rename_folder``, ``delete_folder``,
    ``move_instance``, ``set_field``, plus ``release`` for the AI and
    price paths. Calls are recorded on ``calls`` so tests can assert on
    them; ``folders`` and ``fields`` are tracked so multi-step
    scenarios (e.g. delete-folder move-then-delete) can be exercised.
    """

    def __init__(self):
        self.calls: list[tuple] = []
        self.folders: dict[int, dict] = {}  # id -> {id, name}
        self.fields: dict[int, str] = {}  # instance_id -> {field_id: value}
        self._next_folder_id = 1000

    # -- lifecycle (matches the real client's teardown contract) -------

    def close(self) -> None:
        self.closed = True

    # -- reads (minimal — enough for AI/price paths) -------------------

    def release(self, release_id: int) -> dict:
        self.calls.append(("release", release_id))
        return {"id": release_id, "notes": "", "lowest_price": None}

    # -- writes ---------------------------------------------------------

    def create_folder(self, username: str, name: str) -> dict:
        folder_id = self._next_folder_id
        self._next_folder_id += 1
        folder = {"id": folder_id, "name": name}
        self.folders[folder_id] = folder
        self.calls.append(("create_folder", username, name))
        return folder

    def rename_folder(self, username: str, folder_id: int, name: str) -> dict:
        self.folders[folder_id] = {"id": folder_id, "name": name}
        self.calls.append(("rename_folder", username, folder_id, name))
        return self.folders[folder_id]

    def delete_folder(self, username: str, folder_id: int) -> None:
        self.folders.pop(folder_id, None)
        self.calls.append(("delete_folder", username, folder_id))

    def move_instance(
        self,
        username: str,
        folder_id: int,
        release_id: int,
        instance_id: int,
        to_folder_id: int,
    ) -> None:
        self.calls.append(
            ("move_instance", username, folder_id, release_id, instance_id, to_folder_id)
        )

    def set_field(
        self,
        username: str,
        folder_id: int,
        release_id: int,
        instance_id: int,
        field_id: int,
        value: str,
    ) -> None:
        self.fields.setdefault(instance_id, {})[field_id] = value
        self.calls.append(
            ("set_field", username, folder_id, release_id, instance_id, field_id, value)
        )


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
def fake_discogs():
    """A blank ``FakeDiscogs`` for tests that need to inject one explicitly."""
    return FakeDiscogs()


@pytest.fixture
def client(seeded, monkeypatch):
    """Flask test client with ``lib.web.get_discogs`` patched to return a
    ``FakeDiscogs``. Tests can grab the active fake via
    ``client.application``'s ``g.discogs`` inside an app context, or by
    adding a parallel fixture that yields ``(client, fake)``.
    """
    from lib import web

    fake = FakeDiscogs()
    monkeypatch.setattr(web, "get_discogs", lambda: fake)
    web.app.config["TESTING"] = True
    with web.app.test_client() as client:
        yield client


@pytest.fixture
def client_with_fake(seeded, monkeypatch):
    """Like ``client`` but yields ``(client, fake)`` so tests can assert
    on the ``FakeDiscogs`` instance the client fixture wired in.

    Used by A2.4's ``api_field`` clear-field consistency test, which
    needs to compare the local DB write against what was sent to the
    Discogs fake.
    """
    from lib import web

    fake = FakeDiscogs()
    monkeypatch.setattr(web, "get_discogs", lambda: fake)
    web.app.config["TESTING"] = True
    with web.app.test_client() as client:
        yield client, fake
