"""Flask web app: browse the mirrored collection."""

from collections import Counter
from datetime import datetime, timedelta, timezone

import io

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_file, url_for

from lib import config, db
from lib.sync import FIELD_MEDIA, FIELD_NOTES, FIELD_SLEEVE, FIELD_STYLE, FIELD_SUMMARY

PRICE_MAX_AGE = timedelta(days=7)
UNCATEGORIZED_ID = 1

EDITABLE_FIELDS = {
    "style": FIELD_STYLE,
    "summary": FIELD_SUMMARY,
    "notes": FIELD_NOTES,
    "media_condition": FIELD_MEDIA,
    "sleeve_condition": FIELD_SLEEVE,
}

MEDIA_CONDITIONS = [
    "Mint (M)", "Near Mint (NM or M-)", "Very Good Plus (VG+)", "Very Good (VG)",
    "Good Plus (G+)", "Good (G)", "Fair (F)", "Poor (P)",
]
SLEEVE_CONDITIONS = ["Generic", "No Cover"] + MEDIA_CONDITIONS

# Pastel palette for the folder color chooser (light enough for black text).
PALETTE = [
    "#f6d3d3", "#f6e3d3", "#f6f0d0", "#e4f0cf", "#d2eed5", "#d0eee8",
    "#d0e6f2", "#d4d9f2", "#e2d4f0", "#f0d3ea", "#e8e8e8", "#f5f5f5",
]

SORT_COLUMNS = {
    "title": "title COLLATE NOCASE",
    "artist": "artist COLLATE NOCASE",
    "year": "year",
    "added": "date_added",
    "price": "p.price",
}

app = Flask(__name__)


def get_conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def get_discogs():
    if "discogs" not in g:
        from lib.discogs import DiscogsClient

        g.discogs = DiscogsClient(config.load_secrets()["discogs_pat"])
    return g.discogs


def folder_list(conn):
    folders = conn.execute(
        "SELECT f.id, f.name, count(i.instance_id) AS count FROM folders f "
        "LEFT JOIN items i ON i.folder_id = f.id GROUP BY f.id ORDER BY f.name COLLATE NOCASE"
    ).fetchall()
    total = conn.execute("SELECT count(*) AS n FROM items").fetchone()["n"]
    return folders, total


@app.context_processor
def inject_constants():
    return {
        "media_conditions": MEDIA_CONDITIONS,
        "sleeve_conditions": SLEEVE_CONDITIONS,
        "palette": PALETTE,
    }


@app.template_filter("folder_color")
def folder_color(folder_id):
    """Custom color if set, else a deterministic pastel (black text stays
    readable); grey for Uncategorized."""
    if "folder_colors" not in g:
        g.folder_colors = {
            r["id"]: r["color"] for r in get_conn().execute("SELECT id, color FROM folders")
        }
    if g.folder_colors.get(folder_id):
        return g.folder_colors[folder_id]
    if folder_id == UNCATEGORIZED_ID:
        return "hsl(0, 0%, 92%)"
    hue = (folder_id * 137.508) % 360
    return f"hsl({hue:.0f}, 65%, 87%)"


def folder_stats(conn, folder_id):
    where, params = ("WHERE i.folder_id = ?", [folder_id]) if folder_id is not None else ("", [])
    stats = conn.execute(
        f"""SELECT count(*) AS n, count(p.price) AS priced, coalesce(sum(p.price), 0) AS total,
                   count(i.style) AS with_style, count(i.summary) AS with_summary,
                   max(i.date_added) AS last_added
            FROM items i LEFT JOIN prices p ON p.release_id = i.release_id {where}""",
        params,
    ).fetchone()
    genres = Counter()
    for row in conn.execute(f"SELECT genres FROM items i {where}", params):
        for genre in (row["genres"] or "").split(", "):
            if genre:
                genres[genre] += 1
    return stats, [g for g, _ in genres.most_common(3)]


@app.route("/")
def index():
    return redirect(url_for("folder_view", folder_id="all"))


@app.route("/folder/<folder_id>")
def folder_view(folder_id):
    conn = get_conn()
    folders, total = folder_list(conn)
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "added")
    direction = "ASC" if request.args.get("dir") == "asc" else "DESC"
    order = SORT_COLUMNS.get(sort, SORT_COLUMNS["added"])

    where, params = [], []
    if folder_id != "all":
        where.append("i.folder_id = ?")
        params.append(int(folder_id))
    if q:
        where.append("(i.title LIKE ? OR i.artist LIKE ? OR i.style LIKE ? OR i.notes LIKE ?)")
        params += [f"%{q}%"] * 4
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    items = conn.execute(
        f"""SELECT i.*, p.price, p.fetched_at AS price_fetched_at, f.name AS folder_name
            FROM items i
            LEFT JOIN prices p ON p.release_id = i.release_id
            JOIN folders f ON f.id = i.folder_id
            {where_sql} ORDER BY {order} {direction}""",
        params,
    ).fetchall()

    current = None
    if folder_id != "all":
        current = conn.execute("SELECT * FROM folders WHERE id = ?", (int(folder_id),)).fetchone()
        if current is None:
            abort(404)

    stats, top_genres = folder_stats(conn, current["id"] if current else None)

    return render_template(
        "collection.html",
        folders=folders,
        total=total,
        current=current,
        items=items,
        stats=stats,
        top_genres=top_genres,
        q=q,
        sort=sort,
        direction=direction.lower(),
        last_sync=db.get_setting(conn, "last_sync"),
    )


@app.route("/item/<int:instance_id>")
def item_view(instance_id):
    conn = get_conn()
    item = conn.execute(
        """SELECT i.*, f.name AS folder_name, p.price, pu.paid_price FROM items i
           JOIN folders f ON f.id = i.folder_id
           LEFT JOIN prices p ON p.release_id = i.release_id
           LEFT JOIN purchases pu ON pu.instance_id = i.instance_id
           WHERE i.instance_id = ?""",
        (instance_id,),
    ).fetchone()
    if item is None:
        abort(404)
    folders, _ = folder_list(conn)
    if request.args.get("partial"):
        return render_template("_detail.html", item=item, folders=folders)
    return render_template("item.html", item=item, folders=folders)


@app.route("/api/price/<int:release_id>")
def price(release_id):
    """Cached release price; fetches from Discogs when missing or stale."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM prices WHERE release_id = ?", (release_id,)).fetchone()
    if row is not None:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < PRICE_MAX_AGE:
            return jsonify({"price": row["price"], "cached": True})
    release = get_discogs().release(release_id)
    with conn:
        conn.execute(
            "INSERT INTO prices (release_id, price, num_for_sale, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(release_id) DO UPDATE SET price = excluded.price, "
            "num_for_sale = excluded.num_for_sale, fetched_at = excluded.fetched_at",
            (
                release_id,
                release.get("lowest_price"),
                release.get("num_for_sale"),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
    return jsonify({"price": release.get("lowest_price"), "cached": False})


def _require_item(conn, instance_id: int):
    item = conn.execute("SELECT * FROM items WHERE instance_id = ?", (instance_id,)).fetchone()
    if item is None:
        abort(404)
    return item


def _username(conn) -> str:
    username = db.get_setting(conn, "username")
    if not username:
        abort(500, "no username in db — run `records sync` first")
    return username


def _handle_discogs_error(exc):
    if request.path.startswith("/api/"):
        return jsonify({"error": str(exc)}), 502
    raise exc


from lib.discogs import DiscogsError  # noqa: E402

app.register_error_handler(DiscogsError, _handle_discogs_error)


@app.post("/api/move")
def api_move():
    data = request.get_json()
    conn = get_conn()
    item = _require_item(conn, int(data["instance_id"]))
    to_folder = int(data["to_folder_id"])
    if conn.execute("SELECT 1 FROM folders WHERE id = ?", (to_folder,)).fetchone() is None:
        abort(400, "unknown folder")
    if to_folder != item["folder_id"]:
        get_discogs().move_instance(
            _username(conn), item["folder_id"], item["release_id"], item["instance_id"], to_folder
        )
        with conn:
            conn.execute(
                "UPDATE items SET folder_id = ? WHERE instance_id = ?",
                (to_folder, item["instance_id"]),
            )
    return jsonify({"ok": True})


@app.post("/api/field")
def api_field():
    data = request.get_json()
    field = data["field"]
    if field not in EDITABLE_FIELDS:
        abort(400, "unknown field")
    value = (data.get("value") or "").strip()
    conn = get_conn()
    item = _require_item(conn, int(data["instance_id"]))
    get_discogs().set_field(
        _username(conn),
        item["folder_id"],
        item["release_id"],
        item["instance_id"],
        EDITABLE_FIELDS[field],
        value,
    )
    with conn:
        conn.execute(
            f"UPDATE items SET {field} = ? WHERE instance_id = ?",
            (value or None, item["instance_id"]),
        )
    return jsonify({"ok": True})


@app.post("/api/paid")
def api_paid():
    """App-local paid price — never sent to Discogs."""
    data = request.get_json()
    conn = get_conn()
    item = _require_item(conn, int(data["instance_id"]))
    raw = (str(data.get("value") or "")).strip().lstrip("$")
    with conn:
        if not raw:
            conn.execute("DELETE FROM purchases WHERE instance_id = ?", (item["instance_id"],))
        else:
            try:
                value = float(raw)
            except ValueError:
                abort(400, "paid price must be a number")
            conn.execute(
                "INSERT INTO purchases (instance_id, paid_price) VALUES (?, ?) "
                "ON CONFLICT(instance_id) DO UPDATE SET paid_price = excluded.paid_price",
                (item["instance_id"], value),
            )
    return jsonify({"ok": True})


@app.post("/api/folders")
def api_create_folder():
    name = (request.get_json().get("name") or "").strip()
    if not name:
        abort(400, "empty name")
    conn = get_conn()
    created = get_discogs().create_folder(_username(conn), name)
    with conn:
        conn.execute(
            "INSERT INTO folders (id, name, count) VALUES (?, ?, 0)", (created["id"], created["name"])
        )
    return jsonify({"ok": True, "id": created["id"]})


@app.post("/api/folders/<int:folder_id>/rename")
def api_rename_folder(folder_id):
    if folder_id in (0, UNCATEGORIZED_ID):
        abort(400, "this folder cannot be renamed")
    name = (request.get_json().get("name") or "").strip()
    if not name:
        abort(400, "empty name")
    conn = get_conn()
    get_discogs().rename_folder(_username(conn), folder_id, name)
    with conn:
        conn.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
    return jsonify({"ok": True})


@app.post("/api/folders/<int:folder_id>/color")
def api_folder_color(folder_id):
    """App-local only — Discogs has no notion of folder colors."""
    color = request.get_json().get("color") or None
    if color is not None and color not in PALETTE:
        abort(400, "color not in palette")
    conn = get_conn()
    with conn:
        conn.execute("UPDATE folders SET color = ? WHERE id = ?", (color, folder_id))
    return jsonify({"ok": True})


@app.post("/api/folders/<int:folder_id>/delete")
def api_delete_folder(folder_id):
    if folder_id in (0, UNCATEGORIZED_ID):
        abort(400, "this folder cannot be deleted")
    conn = get_conn()
    move_to = int(request.get_json().get("move_to") or UNCATEGORIZED_ID)
    if move_to == folder_id or conn.execute(
        "SELECT 1 FROM folders WHERE id = ?", (move_to,)
    ).fetchone() is None:
        abort(400, "invalid destination folder")
    username = _username(conn)
    discogs = get_discogs()
    items = conn.execute("SELECT * FROM items WHERE folder_id = ?", (folder_id,)).fetchall()
    for item in items:  # Discogs only deletes empty folders
        discogs.move_instance(
            username, folder_id, item["release_id"], item["instance_id"], move_to
        )
        with conn:
            conn.execute(
                "UPDATE items SET folder_id = ? WHERE instance_id = ?",
                (move_to, item["instance_id"]),
            )
    discogs.delete_folder(username, folder_id)
    with conn:
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    return jsonify({"ok": True, "moved": len(items)})


@app.post("/api/suggest_folder")
def api_suggest_folder():
    from lib.ai import AIError, classify_item

    client = _ai_client()
    if client is None:
        return jsonify({"error": "no OpenRouter key in secrets.yaml — AI features are disabled"}), 503
    conn = get_conn()
    item = dict(_require_item(conn, int(request.get_json()["instance_id"])))
    folders = {
        f["name"]: f["id"]
        for f in conn.execute("SELECT * FROM folders WHERE id != ?", (UNCATEGORIZED_ID,))
    }
    try:
        result = classify_item(client, item, list(folders))
    except AIError as e:
        return jsonify({"error": str(e)}), 502
    name = result.get("folder", "none")
    if name not in folders:
        return jsonify({"error": f"no confident suggestion ({name})"}), 404
    return jsonify(
        {"folder_id": folders[name], "folder": name, "reason": result.get("reason", "")}
    )


def _png_response(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


def _divider_image(conn, folder_id: int):
    from lib import labels

    folder = conn.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if folder is None:
        abort(404)
    _stats, top_genres = folder_stats(conn, folder_id)
    genre_line = " · ".join(top_genres)
    qr_url = f"https://www.discogs.com/user/{_username(conn)}/collection?folder={folder_id}"
    return labels.render_divider(folder["name"], genre_line, qr_url, folder_id=folder_id)


def _sleeve_image(conn, instance_id: int, include_paid: bool = False):
    from lib import labels

    item = dict(_require_item(conn, instance_id))
    if include_paid:
        row = conn.execute(
            "SELECT paid_price FROM purchases WHERE instance_id = ?", (instance_id,)
        ).fetchone()
        item["paid_price"] = row["paid_price"] if row else None
    qr_url = f"https://www.discogs.com/release/{item['release_id']}"
    return labels.render_sleeve(item, qr_url, include_paid=include_paid)


@app.route("/folder/<int:folder_id>/details")
def folder_details(folder_id):
    conn = get_conn()
    folder = conn.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if folder is None:
        abort(404)
    stats, top_genres = folder_stats(conn, folder_id)
    folders, _ = folder_list(conn)
    return render_template(
        "_folder_detail.html", folder=folder, stats=stats, top_genres=top_genres, folders=folders
    )


@app.post("/api/sync")
def api_sync():
    from lib import sync
    from lib.discogs import DiscogsClient

    conn = get_conn()
    discogs = DiscogsClient(config.load_secrets()["discogs_pat"])
    result = sync.pull(discogs, conn, _username(conn))
    return jsonify({"ok": True, **result})


def _ai_client():
    """None when no OpenRouter key is configured — AI features are optional."""
    from lib.ai import OpenRouterClient

    key = config.load_secrets().get("openrouter_key")
    return OpenRouterClient(key) if key else None


@app.post("/api/generate")
def api_generate():
    """Draft style + summary for an item. Returns the draft only — the user
    reviews it in the edit fields and saves explicitly."""
    from lib.ai import AIError, summarize_item

    client = _ai_client()
    if client is None:
        return jsonify({"error": "no OpenRouter key in secrets.yaml — AI features are disabled"}), 503
    conn = get_conn()
    item = dict(_require_item(conn, int(request.get_json()["instance_id"])))
    release_notes = (get_discogs().release(item["release_id"]).get("notes") or "").strip()
    try:
        draft = summarize_item(client, item, release_notes or None)
    except AIError as e:
        return jsonify({"error": str(e)}), 502
    draft["source"] = "discogs notes" if release_notes else "web search"
    return jsonify(draft)


@app.route("/labels/divider/<int:folder_id>.png")
def label_divider(folder_id):
    return _png_response(_divider_image(get_conn(), folder_id))


@app.route("/labels/sleeve/<int:instance_id>.png")
def label_sleeve(instance_id):
    include_paid = request.args.get("paid") == "1"
    return _png_response(_sleeve_image(get_conn(), instance_id, include_paid=include_paid))


@app.post("/api/print")
def api_print():
    from lib import labels

    data = request.get_json()
    kind = data["type"]
    conn = get_conn()
    include_paid = bool(data.get("paid"))
    if kind == "divider":
        images = [_divider_image(conn, int(data["id"]))]
    elif kind == "sleeve":
        images = [_sleeve_image(conn, int(data["id"]), include_paid=include_paid)]
    elif kind == "sleeves":
        if "ids" in data:  # explicit selection
            ids = [int(i) for i in data["ids"]]
        else:  # whole folder
            ids = [
                r["instance_id"]
                for r in conn.execute(
                    "SELECT instance_id FROM items WHERE folder_id = ? ORDER BY artist, year",
                    (int(data["id"]),),
                )
            ]
        images = [_sleeve_image(conn, i) for i in ids]
    else:
        abort(400, "unknown label type")

    settings = config.load_settings()
    if settings["label_output"] == "pdf":
        from datetime import datetime

        pdf_dir = config.ROOT / settings["pdf_dir"]
        pdf_dir.mkdir(parents=True, exist_ok=True)
        path = pdf_dir / f"labels-{datetime.now():%Y%m%d-%H%M%S}.pdf"
        labels.save_pdf(images, path)
        return jsonify({"ok": True, "printed": len(images), "pdf": str(path)})
    try:
        labels.print_images(images, model=settings["printer_model"])
    except labels.PrintError as e:
        return jsonify({"error": str(e)}), 503
    return jsonify({"ok": True, "printed": len(images)})


@app.template_filter("money")
def money(value):
    return f"${value:,.0f}" if value is not None else ""


@app.template_filter("shortdate")
def shortdate(value):
    return value[:7] if value else ""
