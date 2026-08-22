"""The `records` CLI."""

import argparse
import sys

from lib import config


def cmd_auth(args: argparse.Namespace) -> int:
    from lib.ai import AIError, OpenRouterClient
    from lib.discogs import DiscogsClient, DiscogsError
    from lib.printer import discover

    secrets = config.load_secrets()
    ok = True

    try:
        discogs = DiscogsClient(secrets["discogs_pat"])
        me = discogs.identity()
        username = me["username"]
        total = next(f["count"] for f in discogs.folders(username) if f["id"] == 0)
        print(f"✔ discogs: authenticated as {username} ({total} records)")
    except DiscogsError as e:
        print(f"✘ discogs: {e}")
        ok = False

    if secrets.get("openrouter_key"):
        try:
            ai = OpenRouterClient(secrets["openrouter_key"])
            reply = ai.complete("Reply with exactly: OK", max_tokens=500)
            print(f"✔ openrouter: {ai.model} replied ({reply[:40]})")
        except AIError as e:
            print(f"✘ openrouter: {e}")
            ok = False
    else:
        print("– openrouter: no key in secrets.yaml — AI features disabled")

    printers = discover()
    if printers:
        print(f"✔ printer: found {', '.join(printers)}")
    else:
        print("– printer: no Brother QL found on USB (connect it before printing labels)")

    return 0 if ok else 1


def cmd_sync(args: argparse.Namespace) -> int:
    from lib import db, sync
    from lib.discogs import DiscogsClient

    secrets = config.load_secrets()
    discogs = DiscogsClient(secrets["discogs_pat"])
    username = discogs.identity()["username"]
    conn = db.connect()
    print(f"syncing collection of {username} …")
    result = sync.pull(discogs, conn, username)
    print(f"✔ {result['items']} items in {result['folders']} folders → {config.DB_PATH.name}")

    filled = conn.execute(
        "SELECT count(*) AS n, count(style) AS style, count(summary) AS summary, "
        "count(notes) AS notes FROM items"
    ).fetchone()
    print(
        f"  custom fields: style {filled['style']}/{filled['n']}, "
        f"summary {filled['summary']}/{filled['n']}, notes {filled['notes']}/{filled['n']}"
    )
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    from lib import db
    from lib.ai import AIError, OpenRouterClient, summarize_item
    from lib.discogs import DiscogsClient
    from lib.sync import FIELD_STYLE, FIELD_SUMMARY

    secrets = config.load_secrets()
    if not secrets.get("openrouter_key"):
        sys.exit("no OpenRouter key in secrets.yaml — AI features are disabled")
    conn = db.connect()
    username = db.get_setting(conn, "username")
    if not username:
        sys.exit("run `records sync` first")
    discogs = DiscogsClient(secrets["discogs_pat"])
    client = OpenRouterClient(secrets["openrouter_key"])

    where = "WHERE summary IS NULL" if args.missing else ""
    rows = conn.execute(
        f"SELECT * FROM items {where} ORDER BY artist, year LIMIT ?", (args.limit,)
    ).fetchall()
    if not rows:
        print("nothing to do")
        return 0
    print(f"{'writing to Discogs' if args.write else 'dry run (use --write to save)'} — {len(rows)} item(s)\n")

    for row in rows:
        item = dict(row)
        try:
            release_notes = (discogs.release(item["release_id"]).get("notes") or "").strip()
            draft = summarize_item(client, item, release_notes or None)
        except AIError as e:
            print(f"✘ {item['title']}: {e}")
            continue
        source = "discogs" if release_notes else "web"
        print(f"— {item['title']} ({item['artist']}) [{source}]")
        print(f"  style:   {draft['style']}")
        print(f"  summary: {draft['summary']}")
        if args.write:
            for field_id, column, value in (
                (FIELD_STYLE, "style", draft["style"]),
                (FIELD_SUMMARY, "summary", draft["summary"]),
            ):
                discogs.set_field(
                    username, item["folder_id"], item["release_id"], item["instance_id"],
                    field_id, value,
                )
                with conn:
                    conn.execute(
                        f"UPDATE items SET {column} = ? WHERE instance_id = ?",
                        (value, item["instance_id"]),
                    )
            print("  ✔ saved")
        print()
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    from lib import db
    from lib.ai import AIError, OpenRouterClient, classify_item
    from lib.discogs import DiscogsClient

    secrets = config.load_secrets()
    if not secrets.get("openrouter_key"):
        sys.exit("no OpenRouter key in secrets.yaml — AI features are disabled")
    conn = db.connect()
    client = OpenRouterClient(secrets["openrouter_key"])
    discogs = DiscogsClient(secrets["discogs_pat"]) if args.apply else None
    username = db.get_setting(conn, "username")
    folders = {
        f["name"]: f["id"]
        for f in conn.execute("SELECT * FROM folders WHERE id != 1").fetchall()
    }

    if args.review:
        folder = conn.execute(
            "SELECT * FROM folders WHERE name = ? COLLATE NOCASE", (args.review,)
        ).fetchone()
        if folder is None:
            sys.exit(f"no folder named '{args.review}'")
        rows = conn.execute("SELECT * FROM items WHERE folder_id = ?", (folder["id"],)).fetchall()
        print(f"reviewing {len(rows)} items in {folder['name']} …\n")
    else:
        rows = conn.execute("SELECT * FROM items WHERE folder_id = 1 LIMIT ?", (args.limit,)).fetchall()
        print(f"suggesting folders for {len(rows)} uncategorized item(s) …\n")

    for row in rows:
        item = dict(row)
        try:
            result = classify_item(client, item, list(folders))
        except AIError as e:
            print(f"✘ {item['title']}: {e}")
            continue
        suggestion = result.get("folder", "none")
        if args.review:
            if suggestion in folders and folders[suggestion] != item["folder_id"]:
                print(f"? {item['title']} ({item['artist']}) → {suggestion} — {result.get('reason', '')}")
        else:
            print(f"— {item['title']} ({item['artist']}) → {suggestion} — {result.get('reason', '')}")
            if args.apply and suggestion in folders:
                discogs.move_instance(
                    username, item["folder_id"], item["release_id"], item["instance_id"],
                    folders[suggestion],
                )
                with conn:
                    conn.execute(
                        "UPDATE items SET folder_id = ? WHERE instance_id = ?",
                        (folders[suggestion], item["instance_id"]),
                    )
                print("  ✔ moved")
    if args.apply:
        print("\n(moves applied — review in the web app, drag back anything misfiled)")
    else:
        print("\n(no changes made — use --apply to move, or move items in the web app)")
    return 0


def cmd_labels(args: argparse.Namespace) -> int:
    from datetime import datetime
    from pathlib import Path

    from lib import db, labels
    from lib.web import app, folder_stats

    conn = db.connect()
    username = db.get_setting(conn, "username")
    if not username:
        sys.exit("run `records sync` first")

    def divider_image(folder):
        with app.app_context():
            _stats, top_genres = folder_stats(conn, folder["id"])
        qr = f"https://www.discogs.com/user/{username}/collection?folder={folder['id']}"
        return labels.render_divider(
            folder["name"], " · ".join(top_genres), qr, folder_id=folder["id"]
        )

    def find_folder(name):
        folder = conn.execute(
            "SELECT * FROM folders WHERE name = ? COLLATE NOCASE OR id = ?",
            (name, name if name.isdigit() else -1),
        ).fetchone()
        if folder is None:
            sys.exit(f"no folder named '{name}'")
        return folder

    images = []
    if args.divider == "all":
        folders = conn.execute(
            "SELECT f.* FROM folders f WHERE (SELECT count(*) FROM items i "
            "WHERE i.folder_id = f.id) > 0 ORDER BY f.name COLLATE NOCASE"
        ).fetchall()
        for folder in folders:
            images.append((f"divider-{folder['name']}", divider_image(folder)))
    elif args.divider:
        folder = find_folder(args.divider)
        images.append((f"divider-{folder['name']}", divider_image(folder)))
    else:
        folder = find_folder(args.sleeves)
        rows = conn.execute(
            "SELECT * FROM items WHERE folder_id = ? ORDER BY artist, year", (folder["id"],)
        ).fetchall()
        for row in rows:
            item = dict(row)
            qr = f"https://www.discogs.com/release/{item['release_id']}"
            images.append((f"sleeve-{item['instance_id']}", labels.render_sleeve(item, qr)))

    if not images:
        sys.exit("nothing to render")
    settings = config.load_settings()

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        for name_, img in images:
            img.save(outdir / f"{name_}.png")
        print(f"✔ wrote {len(images)} label(s) to {outdir}/")
    elif args.pdf or settings["label_output"] == "pdf":
        path = Path(args.pdf) if args.pdf else (
            config.ROOT / settings["pdf_dir"] / f"labels-{datetime.now():%Y%m%d-%H%M%S}.pdf"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        labels.save_pdf([img for _, img in images], path)
        print(f"✔ wrote {len(images)} label(s) to {path}")
    else:
        try:
            labels.print_images([img for _, img in images], model=settings["printer_model"])
        except labels.PrintError as e:
            sys.exit(f"print failed: {e} (use --pdf FILE or --out DIR instead)")
        print(f"✔ printed {len(images)} label(s)")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    """Export the app-local data Discogs can't restore: paid prices, folder colors."""
    import json
    from datetime import datetime, timezone

    from lib import db

    conn = db.connect()
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purchases": {
            str(r["instance_id"]): r["paid_price"]
            for r in conn.execute("SELECT * FROM purchases")
        },
        "folder_colors": {
            str(r["id"]): r["color"]
            for r in conn.execute("SELECT id, color FROM folders WHERE color IS NOT NULL")
        },
    }
    out = args.out or f"backup-{datetime.now():%Y%m%d}.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✔ {len(data['purchases'])} paid price(s), {len(data['folder_colors'])} color(s) → {out}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    import json

    from lib import db

    with open(args.file) as f:
        data = json.load(f)
    conn = db.connect()
    with conn:
        for instance_id, price in data.get("purchases", {}).items():
            conn.execute(
                "INSERT INTO purchases (instance_id, paid_price) VALUES (?, ?) "
                "ON CONFLICT(instance_id) DO UPDATE SET paid_price = excluded.paid_price",
                (int(instance_id), price),
            )
        for folder_id, color in data.get("folder_colors", {}).items():
            conn.execute("UPDATE folders SET color = ? WHERE id = ?", (color, int(folder_id)))
    print(
        f"✔ restored {len(data.get('purchases', {}))} paid price(s), "
        f"{len(data.get('folder_colors', {}))} color(s) from {args.file}"
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from lib.web import app

    app.run(host="127.0.0.1", port=args.port, debug=args.debug)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="records", description="Discogs record collection tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_auth = sub.add_parser("auth", help="verify Discogs, OpenRouter and printer access")
    p_auth.set_defaults(func=cmd_auth)

    p_sync = sub.add_parser("sync", help="pull the full collection from Discogs")
    p_sync.set_defaults(func=cmd_sync)

    p_sum = sub.add_parser("summarize", help="AI-draft Style/Summary for items")
    p_sum.add_argument("--missing", action="store_true", help="only items with no summary yet")
    p_sum.add_argument("--limit", type=int, default=10)
    p_sum.add_argument("--write", action="store_true", help="save drafts to Discogs")
    p_sum.set_defaults(func=cmd_summarize)

    p_cls = sub.add_parser("classify", help="AI folder suggestions")
    p_cls.add_argument("--review", metavar="FOLDER", help="flag items that may not fit this folder")
    p_cls.add_argument("--limit", type=int, default=20)
    p_cls.add_argument("--apply", action="store_true", help="actually move items to suggested folders")
    p_cls.set_defaults(func=cmd_classify)

    p_labels = sub.add_parser("labels", help="print or export labels")
    group = p_labels.add_mutually_exclusive_group(required=True)
    group.add_argument("--divider", metavar="FOLDER", help="divider label for a folder (name, id, or 'all')")
    group.add_argument("--sleeves", metavar="FOLDER", help="sleeve labels for every item in a folder")
    p_labels.add_argument("--out", metavar="DIR", help="write PNGs here instead of printing")
    p_labels.add_argument("--pdf", metavar="FILE", help="write a PDF (one label per page) instead of printing")
    p_labels.set_defaults(func=cmd_labels)

    p_backup = sub.add_parser("backup", help="export app-local data (paid prices, folder colors)")
    p_backup.add_argument("--out", metavar="FILE")
    p_backup.set_defaults(func=cmd_backup)

    p_restore = sub.add_parser("restore", help="restore app-local data from a backup file")
    p_restore.add_argument("file")
    p_restore.set_defaults(func=cmd_restore)

    p_serve = sub.add_parser("serve", help="start the web app")
    p_serve.add_argument("--port", type=int, default=5033)
    p_serve.add_argument("--debug", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    try:
        sys.exit(args.func(args))
    except config.ConfigError as e:
        sys.exit(f"config error: {e}")
