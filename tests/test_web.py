import json


def post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_collection_view_renders(client):
    resp = client.get("/folder/all")
    assert resp.status_code == 200
    assert b"Kind Of Blue" in resp.data
    assert b"jazz" in resp.data


def test_folder_view_404_for_unknown(client):
    assert client.get("/folder/9999").status_code == 404


def test_item_partial_and_page(client):
    assert b"modal-box" not in client.get("/item/100?partial=1").data
    assert client.get("/item/100").status_code == 200
    assert client.get("/item/12345").status_code == 404


def test_field_rejects_unknown_field(client):
    resp = post(client, "/api/field", {"instance_id": 100, "field": "hacker", "value": "x"})
    assert resp.status_code == 400


def test_move_rejects_unknown_folder(client):
    resp = post(client, "/api/move", {"instance_id": 100, "to_folder_id": 9999})
    assert resp.status_code == 400


def test_move_to_same_folder_is_noop(client):
    # no Discogs client is wired in tests: reaching Discogs would error loudly
    resp = post(client, "/api/move", {"instance_id": 100, "to_folder_id": 10})
    assert resp.status_code == 200


def test_paid_price_set_and_clear(client, seeded):
    assert post(client, "/api/paid", {"instance_id": 100, "value": "$12.50"}).status_code == 200
    row = seeded.execute("SELECT paid_price FROM purchases WHERE instance_id = 100").fetchone()
    assert row[0] == 12.5
    assert post(client, "/api/paid", {"instance_id": 100, "value": ""}).status_code == 200
    assert seeded.execute("SELECT count(*) FROM purchases").fetchone()[0] == 0
    assert post(client, "/api/paid", {"instance_id": 100, "value": "abc"}).status_code == 400


def test_folder_color_validation(client, seeded):
    from lib.web import PALETTE

    assert post(client, f"/api/folders/10/color", {"color": PALETTE[0]}).status_code == 200
    assert post(client, f"/api/folders/10/color", {"color": "#123456"}).status_code == 400
    assert post(client, f"/api/folders/10/color", {"color": None}).status_code == 200
    assert seeded.execute("SELECT color FROM folders WHERE id = 10").fetchone()[0] is None


def test_protected_folders_cannot_be_renamed_or_deleted(client):
    assert post(client, "/api/folders/1/rename", {"name": "x"}).status_code == 400
    assert post(client, "/api/folders/1/delete", {"move_to": 10}).status_code == 400
    # deleting into itself is invalid
    assert post(client, "/api/folders/10/delete", {"move_to": 10}).status_code == 400


def test_ai_endpoints_disabled_without_key(client, monkeypatch):
    from lib import web

    monkeypatch.setattr(web.config, "load_secrets", lambda: {"discogs_pat": "x"})
    resp = post(client, "/api/generate", {"instance_id": 100})
    assert resp.status_code == 503
    assert b"disabled" in resp.data
    assert post(client, "/api/suggest_folder", {"instance_id": 100}).status_code == 503


def test_label_previews_render(client):
    assert client.get("/labels/sleeve/100.png").status_code == 200
    resp = client.get("/labels/divider/10.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_crate_view(client):
    resp = client.get("/crate")
    assert resp.status_code == 200
    assert b"crate-data" in resp.data
    assert b'"type": "divider"' in resp.data
    assert b"Kind Of Blue" in resp.data


def test_folder_color_filter_is_deterministic(client):
    from lib.web import app, folder_color

    with app.test_request_context():
        a = folder_color(1244414)
        b = folder_color(1244414)
    assert a == b and a.startswith("hsl(")
