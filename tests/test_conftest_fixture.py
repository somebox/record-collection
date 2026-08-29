"""Smoke tests for the A2.0 Discogs fake fixture.

These tests don't assert on real Discogs behavior — they just prove the
fake is wired into ``client`` and that the methods the write endpoints
call (create_folder, rename_folder, delete_folder, move_instance,
set_field) are recorded so future A2.1–A2.4 tests can build on them.
"""

import json

import pytest

from tests.conftest import FakeDiscogs


def post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.fixture
def client_with_fake(seeded, monkeypatch):
    """Yield ``(client, fake)`` where ``fake`` is the same instance the
    request sees via ``web.get_discogs``."""
    from lib import web

    fake = FakeDiscogs()
    monkeypatch.setattr(web, "get_discogs", lambda: fake)
    web.app.config["TESTING"] = True
    with web.app.test_client() as client:
        yield client, fake


def test_client_uses_injected_fake_for_move(client_with_fake):
    client, fake = client_with_fake
    resp = post(client, "/api/move", {"instance_id": 100, "to_folder_id": 20})
    assert resp.status_code == 200
    assert any(c[0] == "move_instance" for c in fake.calls)
    move = next(c for c in fake.calls if c[0] == "move_instance")
    # (op, username, from_folder, release_id, instance_id, to_folder)
    assert move[1:] == ("tester", 10, 555, 100, 20)


def test_client_uses_injected_fake_for_field(client_with_fake):
    client, fake = client_with_fake
    resp = post(client, "/api/field", {"instance_id": 100, "field": "notes", "value": "hi"})
    assert resp.status_code == 200
    assert any(c[0] == "set_field" for c in fake.calls)
    # (op, username, folder, release, instance, field_id, value)
    assert fake.fields[100]  # recorded value present


def test_client_uses_injected_fake_for_create_folder(client_with_fake, seeded):
    client, fake = client_with_fake
    resp = post(client, "/api/folders", {"name": "ambient"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["id"] in fake.folders
    # Local DB was updated too.
    row = seeded.execute("SELECT name FROM folders WHERE id = ?", (body["id"],)).fetchone()
    assert row["name"] == "ambient"


def test_client_uses_injected_fake_for_rename_folder(client_with_fake):
    client, fake = client_with_fake
    resp = post(client, "/api/folders/10/rename", {"name": "Jazz!"})
    assert resp.status_code == 200
    assert fake.folders[10]["name"] == "Jazz!"


def test_client_uses_injected_fake_for_delete_folder(client_with_fake, seeded):
    client, fake = client_with_fake
    # Move the seeded item (folder 10) out first by deleting folder 10
    # into folder 20. Items in folder 10 are moved then folder 10 removed.
    resp = post(client, "/api/folders/10/delete", {"move_to": 20})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["moved"] == 1
    # Recorded both the move and the delete calls.
    assert any(c[0] == "move_instance" for c in fake.calls)
    assert ("delete_folder", "tester", 10) in fake.calls
    assert 10 not in fake.folders
