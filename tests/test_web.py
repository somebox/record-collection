import json
from datetime import datetime, timedelta, timezone


def post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_collection_view_renders(client):
    resp = client.get("/folder/all")
    assert resp.status_code == 200
    assert b"Kind Of Blue" in resp.data
    assert b"jazz" in resp.data


def test_collection_marks_only_missing_or_old_prices_stale(client, seeded):
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with seeded:
        seeded.execute(
            "INSERT INTO prices (release_id, price, fetched_at) VALUES (555, 20, ?)", (old,)
        )
    assert b'data-stale="1"' in client.get("/folder/all").data

    with seeded:
        seeded.execute(
            "UPDATE prices SET fetched_at = ? WHERE release_id = 555",
            (datetime.now(timezone.utc).isoformat(),),
        )
    assert b'data-stale="0"' in client.get("/folder/all").data


def test_folder_view_404_for_unknown(client):
    assert client.get("/folder/9999").status_code == 404


def test_folder_view_404_for_non_numeric_id(client):
    assert client.get("/folder/abc").status_code == 404


def test_item_partial_and_page(client):
    assert b"modal-box" not in client.get("/item/100?partial=1").data
    assert client.get("/item/100").status_code == 200
    assert client.get("/item/12345").status_code == 404


def test_field_rejects_unknown_field(client):
    resp = post(client, "/api/field", {"instance_id": 100, "field": "hacker", "value": "x"})
    assert resp.status_code == 400


def test_api_field_clear_is_consistent_between_local_and_discogs(
    client_with_fake, seeded
):
    """A2.4: ``api_field`` must not write ``NULL`` locally while writing
    ``""`` to Discogs. The chosen contract is: a cleared field is
    represented as ``NULL`` locally, and the Discogs ``set_field`` call
    is SKIPPED (so the local value matches what was sent to Discogs:
    nothing). Re-sync reconciles any stale Discogs state on the next
    pull.
    """
    client, fake = client_with_fake
    from lib.web import EDITABLE_FIELDS

    # Seed a non-empty value locally so we can observe the clear.
    with seeded:
        seeded.execute(
            "UPDATE items SET style = ? WHERE instance_id = 100",
            ("ambient, quiet",),
        )

    # 1. Setting a non-empty value: both stores get the same string.
    resp = post(client, "/api/field", {"instance_id": 100, "field": "style", "value": "jazzy"})
    assert resp.status_code == 200
    local = seeded.execute(
        "SELECT style FROM items WHERE instance_id = 100"
    ).fetchone()[0]
    assert local == "jazzy"
    assert fake.fields[100][EDITABLE_FIELDS["style"]] == "jazzy"
    set_field_calls_so_far = sum(
        1 for c in fake.calls if c[0] == "set_field"
    )
    assert set_field_calls_so_far == 1

    # 2. Clearing: local goes to NULL and Discogs is NOT called. The
    #    consistency contract is that whatever was sent to Discogs (here:
    #    nothing) matches the local representation (NULL).
    resp = post(client, "/api/field", {"instance_id": 100, "field": "style", "value": ""})
    assert resp.status_code == 200
    local = seeded.execute(
        "SELECT style FROM items WHERE instance_id = 100"
    ).fetchone()[0]
    assert local is None
    set_field_calls_after_clear = sum(
        1 for c in fake.calls if c[0] == "set_field"
    )
    assert set_field_calls_after_clear == set_field_calls_so_far, (
        "cleared field must not produce an additional set_field call"
    )
    # The previously-sent value still sits on the fake, and matches the
    # LAST thing that was actually sent — confirming no divergent write
    # happened during the clear.
    assert fake.fields[100][EDITABLE_FIELDS["style"]] == "jazzy"


def test_move_rejects_unknown_folder(client):
    resp = post(client, "/api/move", {"instance_id": 100, "to_folder_id": 9999})
    assert resp.status_code == 400


def test_move_to_same_folder_is_noop(client_with_fake):
    """Moving an item into the folder it already lives in must be a
    local no-op and must NOT reach Discogs."""
    client, fake = client_with_fake
    resp = post(client, "/api/move", {"instance_id": 100, "to_folder_id": 10})
    assert resp.status_code == 200
    assert fake.calls == []


def test_paid_price_set_and_clear(client, seeded):
    assert post(client, "/api/paid", {"instance_id": 100, "value": "$12.50"}).status_code == 200
    row = seeded.execute("SELECT paid_price FROM purchases WHERE instance_id = 100").fetchone()
    assert row[0] == 12.5
    assert post(client, "/api/paid", {"instance_id": 100, "value": ""}).status_code == 200
    assert seeded.execute("SELECT count(*) FROM purchases").fetchone()[0] == 0
    assert post(client, "/api/paid", {"instance_id": 100, "value": "abc"}).status_code == 400


def test_paid_price_rejects_negative_and_oversized_values(client, seeded):
    """A4.4: ``api_paid`` must reject negative and absurdly large paid
    prices with a 400 response and must NOT write the bad value. The
    chosen bound is ``lib.web.PAID_PRICE_MAX`` (currently 1_000_000);
    see that constant for the rationale."""
    from lib.web import PAID_PRICE_MAX

    # Negative price: rejected, no row written.
    resp = post(client, "/api/paid", {"instance_id": 100, "value": "-1.00"})
    assert resp.status_code == 400
    assert seeded.execute("SELECT count(*) FROM purchases").fetchone()[0] == 0

    # Just below the upper bound is accepted (boundary check).
    boundary = PAID_PRICE_MAX - 1
    assert post(
        client, "/api/paid", {"instance_id": 100, "value": str(boundary)}
    ).status_code == 200
    row = seeded.execute(
        "SELECT paid_price FROM purchases WHERE instance_id = 100"
    ).fetchone()
    assert row[0] == boundary

    # At the upper bound: still accepted.
    assert post(
        client, "/api/paid", {"instance_id": 100, "value": str(PAID_PRICE_MAX)}
    ).status_code == 200

    # One cent over the upper bound: rejected.
    over = PAID_PRICE_MAX + 0.01
    resp = post(client, "/api/paid", {"instance_id": 100, "value": str(over)})
    assert resp.status_code == 400
    # The previously-accepted boundary value is still in place; the
    # over-boundary write must not have overwritten it.
    row = seeded.execute(
        "SELECT paid_price FROM purchases WHERE instance_id = 100"
    ).fetchone()
    assert row[0] == PAID_PRICE_MAX


def test_display_year_override_set_validate_and_clear(client, seeded):
    original_label = client.get("/labels/sleeve/100.png").data
    assert post(client, "/api/year", {"instance_id": 100, "value": "1958"}).status_code == 200
    assert seeded.execute("SELECT year FROM year_overrides WHERE instance_id=100").fetchone()[0] == 1958
    assert b"1958" in client.get("/item/100?partial=1").data
    assert b"1958" in client.get("/folder/all").data
    assert client.get("/labels/sleeve/100.png").data != original_label

    assert post(client, "/api/year", {"instance_id": 100, "value": "nineteen"}).status_code == 400
    assert post(client, "/api/year", {"instance_id": 100, "value": "10000"}).status_code == 400
    assert post(client, "/api/year", {"instance_id": 100, "value": ""}).status_code == 200
    assert seeded.execute("SELECT count(*) FROM year_overrides").fetchone()[0] == 0


def test_folder_color_validation(client, seeded):
    from lib.web import PALETTE

    # Set to PALETTE[0]: must persist that exact color (not just any 200).
    assert post(client, f"/api/folders/10/color", {"color": PALETTE[0]}).status_code == 200
    assert seeded.execute("SELECT color FROM folders WHERE id = 10").fetchone()[0] == PALETTE[0]

    # Out-of-palette value rejected.
    assert post(client, f"/api/folders/10/color", {"color": "#123456"}).status_code == 400

    # Clear: must persist as NULL (not just any 200).
    assert post(client, f"/api/folders/10/color", {"color": None}).status_code == 200
    assert seeded.execute("SELECT color FROM folders WHERE id = 10").fetchone()[0] is None


def test_protected_folders_cannot_be_renamed_or_deleted(client):
    assert post(client, "/api/folders/1/rename", {"name": "x"}).status_code == 400
    assert post(client, "/api/folders/1/delete", {"move_to": 10}).status_code == 400
    # deleting into itself is invalid
    assert post(client, "/api/folders/10/delete", {"move_to": 10}).status_code == 400


def test_api_delete_folder_documents_partial_update_risk_and_still_works(client, seeded):
    """A2.3 / D1: ``api_delete_folder`` is documented (not compensated) for
    its partial-update risk. This test guards the documented behavior:
    the docstring must remain, and a normal happy-path delete must still
    move items remotely+locally and remove the folder.

    No failure-injection here — the action-plan default for D1 is option
    (a) document, so the contract being tested is "the happy path still
    works and the docstring is still in place to explain the risk".
    """
    from lib import web

    # 1. The docstring is present and explains the partial-update risk.
    doc = web.api_delete_folder.__doc__ or ""
    assert "partial-update risk" in doc.lower() or "partial update risk" in doc.lower()
    assert "re-sync" in doc.lower() or "resync" in doc.lower()
    # 2. The function is not documented as compensating; that would mean
    #    D1 was changed away from option (a).
    assert "rollback" not in doc.lower() or "no compensating" in doc.lower() or "not the default" in doc.lower()

    # 3. Happy path: deleting folder 10 (which contains item 100) into
    #    folder 20 still moves the item and removes the folder.
    resp = post(client, "/api/folders/10/delete", {"move_to": 20})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["moved"] == 1

    # 4. Local state: item 100 now lives in folder 20; folder 10 is gone.
    row = seeded.execute(
        "SELECT folder_id FROM items WHERE instance_id = 100"
    ).fetchone()
    assert row[0] == 20
    assert seeded.execute("SELECT 1 FROM folders WHERE id = 10").fetchone() is None


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


def test_web_divider_matches_cli_helper_construction(client, seeded):
    """A4.6: the web route ``/labels/divider/<id>.png`` and the CLI's
    ``records labels --divider`` must produce byte-identical divider
    images for the same folder + username. Both call sites now go
    through ``labels.divider_qr_url`` + ``labels.join_genre_line``; this
    test guards the refactor by rendering both sides and comparing
    bytes."""
    from io import BytesIO

    from PIL import Image

    from lib import labels, web

    # 1. Hit the web route and decode the PNG.
    web_bytes = client.get("/labels/divider/10.png").data
    web_img = Image.open(BytesIO(web_bytes)).convert("L")

    # 2. Reconstruct what the CLI path would produce: fetch folder
    #    metadata, compute genre line, build QR URL via the same helper,
    #    and render with the same ``render_divider`` function.
    folder = seeded.execute("SELECT * FROM folders WHERE id = ?", (10,)).fetchone()
    _stats, top_genres = web.folder_stats(seeded, 10)
    helper_img = labels.render_divider(
        folder["name"],
        labels.join_genre_line(top_genres),
        labels.divider_qr_url("tester", 10),
        folder_id=10,
    )
    assert web_img.tobytes() == helper_img.tobytes()


def test_crate_view(client):
    resp = client.get("/crate")
    assert resp.status_code == 200
    assert b"crate-data" in resp.data
    assert b'"type": "divider"' in resp.data
    assert b"Kind Of Blue" in resp.data


def test_discogs_client_is_closed_at_request_teardown():
    from flask import g

    from lib.web import app

    class FakeDiscogs:
        closed = False

        def close(self):
            self.closed = True

    discogs = FakeDiscogs()
    with app.test_request_context():
        g.discogs = discogs
    assert discogs.closed


def test_folder_color_filter_is_deterministic(client):
    from lib.web import app, folder_color

    with app.test_request_context():
        a = folder_color(1244414)
        b = folder_color(1244414)
    assert a == b and a.startswith("hsl(")


def test_api_print_sleeves_empty_ids_returns_400(client):
    resp = post(client, "/api/print", {"type": "sleeves", "ids": []})
    assert resp.status_code == 400


def test_api_print_sleeves_empty_folder_returns_400(client):
    resp = post(client, "/api/print", {"type": "sleeves", "id": 20})
    assert resp.status_code == 400


# Malformed-body 400 tests for every POST write handler (A1.2 / §2.6.1).
# Each handler must return 400, not 500, on null body or missing required key.


def _post_raw(client, path, body):
    return client.post(path, data=body, content_type="application/json")


def test_api_move_null_body_returns_400(client):
    assert _post_raw(client, "/api/move", "null").status_code == 400


def test_api_move_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/move", "{}").status_code == 400


def test_api_field_null_body_returns_400(client):
    assert _post_raw(client, "/api/field", "null").status_code == 400


def test_api_field_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/field", "{}").status_code == 400


def test_api_paid_null_body_returns_400(client):
    assert _post_raw(client, "/api/paid", "null").status_code == 400


def test_api_paid_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/paid", "{}").status_code == 400


def test_api_year_null_body_returns_400(client):
    assert _post_raw(client, "/api/year", "null").status_code == 400


def test_api_year_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/year", "{}").status_code == 400


def test_api_create_folder_null_body_returns_400(client):
    assert _post_raw(client, "/api/folders", "null").status_code == 400


def test_api_create_folder_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/folders", "{}").status_code == 400


def test_api_rename_folder_null_body_returns_400(client):
    # Even protected-folder rejection happens before body parse — either way 400.
    assert _post_raw(client, "/api/folders/10/rename", "null").status_code == 400


def test_api_rename_folder_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/folders/10/rename", "{}").status_code == 400


def test_api_folder_color_null_body_returns_400(client):
    # `color` is the only key and is not required, so missing keys {} → 200
    # (clears the color). `null` body should still 400.
    assert _post_raw(client, "/api/folders/10/color", "null").status_code == 400


def test_api_delete_folder_null_body_returns_400(client):
    assert _post_raw(client, "/api/folders/10/delete", "null").status_code == 400


def test_api_delete_folder_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/folders/10/delete", "{}").status_code == 400


def test_api_suggest_folder_null_body_returns_400(client):
    # AI is disabled in tests (no key) so the order is: AI check first, then
    # body validation. With no key, this stays a 503 — that's the existing
    # AI-disabled path. We need to wire a key to exercise body validation.
    from lib import web

    original = web.config.load_secrets
    web.config.load_secrets = lambda: {"openrouter_key": "test"}
    try:
        assert _post_raw(client, "/api/suggest_folder", "null").status_code == 400
    finally:
        web.config.load_secrets = original


def test_api_suggest_folder_missing_keys_returns_400(client):
    from lib import web

    original = web.config.load_secrets
    web.config.load_secrets = lambda: {"openrouter_key": "test"}
    try:
        assert _post_raw(client, "/api/suggest_folder", "{}").status_code == 400
    finally:
        web.config.load_secrets = original


def test_api_generate_null_body_returns_400(client):
    from lib import web

    original = web.config.load_secrets
    web.config.load_secrets = lambda: {"openrouter_key": "test"}
    try:
        assert _post_raw(client, "/api/generate", "null").status_code == 400
    finally:
        web.config.load_secrets = original


def test_api_generate_missing_keys_returns_400(client):
    from lib import web

    original = web.config.load_secrets
    web.config.load_secrets = lambda: {"openrouter_key": "test"}
    try:
        assert _post_raw(client, "/api/generate", "{}").status_code == 400
    finally:
        web.config.load_secrets = original


def test_api_print_null_body_returns_400(client):
    assert _post_raw(client, "/api/print", "null").status_code == 400


def test_api_print_missing_keys_returns_400(client):
    assert _post_raw(client, "/api/print", "{}").status_code == 400


def test_api_print_sleeve_returns_400_on_label_layout_error(client, monkeypatch):
    """A3.3: when ``_header_layout`` raises ``LabelLayoutError`` because
    the supplied content cannot be laid out (pathological title, byline,
    or style), the print endpoint must return 400, not 500. We force
    the error by stubbing the renderer's ``_header_layout`` so any call
    raises ``LabelLayoutError``."""
    from lib import labels, web

    def _boom(*_args, **_kwargs):
        raise labels.LabelLayoutError("header cannot fit at the minimum text size")

    monkeypatch.setattr(labels, "_header_layout", _boom)
    resp = post(client, "/api/print", {"type": "sleeve", "id": 100})
    assert resp.status_code == 400
    assert b"header cannot fit" in resp.data


def test_api_print_sleeves_returns_400_on_label_layout_error(client, monkeypatch):
    """A3.3: same contract for the bulk ``sleeves`` path. The first item
    that triggers the layout error must short-circuit the render to a
    400 response."""
    from lib import labels

    def _boom(*_args, **_kwargs):
        raise labels.LabelLayoutError("header cannot fit at the minimum text size")

    monkeypatch.setattr(labels, "_header_layout", _boom)
    resp = post(client, "/api/print", {"type": "sleeves", "id": 10})
    assert resp.status_code == 400
    assert b"header cannot fit" in resp.data


def test_label_preview_returns_400_on_label_layout_error(client, monkeypatch):
    """A3.3: GET ``/labels/sleeve/<id>.png`` also renders a label and
    would 500 on a layout error. The Flask error handler must return
    400. (The divider route does not call ``_header_layout`` so the
    error is structurally unreachable there; we cover it for symmetry
    by stubbing ``render_divider`` directly.)"""
    from lib import labels

    def _boom(*_args, **_kwargs):
        raise labels.LabelLayoutError("header cannot fit at the minimum text size")

    monkeypatch.setattr(labels, "_header_layout", _boom)
    resp = client.get("/labels/sleeve/100.png")
    assert resp.status_code == 400
    assert b"header cannot fit" in resp.data

    monkeypatch.setattr(labels, "render_divider", _boom)
    resp = client.get("/labels/divider/10.png")
    assert resp.status_code == 400
    assert b"header cannot fit" in resp.data


def test_api_move_non_numeric_instance_id_returns_400(client):
    """A POST with a non-numeric ``instance_id`` must return 400, not 500.

    The handler used to call ``int(data["instance_id"])`` directly, which
    raised ``ValueError`` for strings like ``"abc"`` and surfaced as a
    500. The ``_require_int`` helper now coerces with a 400 error
    response instead.
    """
    resp = post(client, "/api/move", {"instance_id": "abc", "to_folder_id": 10})
    assert resp.status_code == 400
    assert b"integer" in resp.data


def test_api_paid_non_numeric_instance_id_returns_400(client):
    """Same 400-not-500 contract for ``/api/paid``."""
    resp = post(client, "/api/paid", {"instance_id": "abc", "value": "12.50"})
    assert resp.status_code == 400
    assert b"integer" in resp.data


def test_api_print_non_numeric_id_returns_400(client):
    """Same 400-not-500 contract for ``/api/print`` (``sleeve`` branch)."""
    resp = post(client, "/api/print", {"type": "sleeve", "id": "abc"})
    assert resp.status_code == 400
    assert b"integer" in resp.data
