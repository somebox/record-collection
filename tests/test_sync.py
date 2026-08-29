from lib import sync


class FakeDiscogs:
    def folders(self, username):
        return [
            {"id": 0, "name": "All", "count": 2},
            {"id": 1, "name": "Uncategorized", "count": 1},
            {"id": 10, "name": "jazz", "count": 1},
        ]

    def collection_items(self, username, folder_id=0):
        return [
            {
                "instance_id": 100,
                "folder_id": 10,
                "date_added": "2017-09-23T19:31:36-07:00",
                "notes": [
                    {"field_id": 1, "value": "Mint (M)"},
                    {"field_id": 3, "value": "gift from Ana"},
                    {"field_id": 5, "value": "modal, cool"},
                ],
                "basic_information": {
                    "id": 555,
                    "title": "Kind Of Blue",
                    "year": 1959,
                    "artists": [{"name": "Miles Davis (2)", "anv": ""}],
                    "labels": [{"name": "Columbia", "catno": "CL 1355"}],
                    "genres": ["Jazz"],
                    "styles": ["Modal"],
                    "thumb": "t.jpg",
                    "cover_image": "c.jpg",
                },
            },
            {
                "instance_id": 200,
                "folder_id": 1,
                "date_added": "2020-01-01T00:00:00-07:00",
                "basic_information": {
                    "id": 777,
                    "title": "Mystery",
                    "year": 0,
                    "artists": [{"name": "Unknown Artist", "anv": ""}],
                    "labels": [],
                    "genres": [],
                    "styles": [],
                },
            },
        ]


def test_pull_maps_fields_and_cleans_artists(conn):
    result = sync.pull(FakeDiscogs(), conn, "tester")
    assert result == {"folders": 2, "items": 2}

    item = conn.execute("SELECT * FROM items WHERE instance_id = 100").fetchone()
    assert item["artist"] == "Miles Davis"  # "(2)" suffix stripped
    assert item["media_condition"] == "Mint (M)"
    assert item["notes"] == "gift from Ana"
    assert item["style"] == "modal, cool"
    assert item["summary"] is None
    assert item["label"] == "Columbia"

    bare = conn.execute("SELECT * FROM items WHERE instance_id = 200").fetchone()
    assert bare["year"] is None  # 0 stored as NULL
    assert bare["label"] is None


def test_pull_preserves_folder_colors(conn):
    sync.pull(FakeDiscogs(), conn, "tester")
    with conn:
        conn.execute("UPDATE folders SET color = '#d0e6f2' WHERE id = 10")
    sync.pull(FakeDiscogs(), conn, "tester")  # full rebuild
    assert conn.execute("SELECT color FROM folders WHERE id = 10").fetchone()[0] == "#d0e6f2"


def test_pull_replaces_stale_items(conn):
    with conn:
        conn.execute("INSERT INTO folders (id, name, count) VALUES (1, 'Uncategorized', 0)")
        conn.execute(
            "INSERT INTO items (instance_id, release_id, folder_id, title, artist) "
            "VALUES (999, 1, 1, 'Gone', 'Nobody')"
        )
    sync.pull(FakeDiscogs(), conn, "tester")
    assert conn.execute("SELECT count(*) FROM items WHERE instance_id = 999").fetchone()[0] == 0


def test_purchases_survive_pull(conn):
    with conn:
        conn.execute("INSERT INTO purchases (instance_id, paid_price) VALUES (100, 25.0)")
    sync.pull(FakeDiscogs(), conn, "tester")
    assert conn.execute("SELECT paid_price FROM purchases WHERE instance_id = 100").fetchone()[0] == 25.0


def test_year_overrides_survive_pull(conn):
    with conn:
        conn.execute("INSERT INTO year_overrides (instance_id, year) VALUES (100, 1958)")
    sync.pull(FakeDiscogs(), conn, "tester")
    assert conn.execute("SELECT year FROM year_overrides WHERE instance_id = 100").fetchone()[0] == 1958


def test_artist_names_skips_entries_with_no_name():
    """An artist entry with neither anv nor name should be skipped, not crash."""
    assert sync._artist_names([{"anv": "", "name": "Miles Davis (2)"}]) == "Miles Davis"
    assert sync._artist_names([{"anv": "MD", "name": "ignored"}]) == "MD"
    # no name, no anv -> skip
    assert sync._artist_names([{"anv": "", "name": ""}]) == ""
    assert sync._artist_names([{"anv": "", "name": ""}, {"name": "Other"}]) == "Other"
    # entirely missing keys -> skip
    assert sync._artist_names([{}]) == ""
    assert sync._artist_names([{}, {"name": "Solo"}]) == "Solo"


class FakeDiscogsBadArtist(FakeDiscogs):
    def collection_items(self, username, folder_id=0):
        return [
            {
                "instance_id": 300,
                "folder_id": 1,
                "date_added": "2020-01-01T00:00:00-07:00",
                "basic_information": {
                    "id": 888,
                    "title": "Anonymous",
                    "year": 2000,
                    "artists": [{"anv": "", "name": ""}],  # malformed: no name
                    "labels": [],
                    "genres": [],
                    "styles": [],
                },
            },
        ]


def test_pull_skips_malformed_artist_entry(conn):
    """A pull with a malformed artist entry should not crash; the row is
    stored with an empty artist string."""
    result = sync.pull(FakeDiscogsBadArtist(), conn, "tester")
    assert result == {"folders": 2, "items": 1}
    row = conn.execute("SELECT artist FROM items WHERE instance_id = 300").fetchone()
    assert row["artist"] == ""
