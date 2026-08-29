"""Tests for CLI command guards (A2.5, A2.6)."""

import argparse
import json

import pytest

from lib import cli


# -- A2.5: cmd_auth skips gracefully when folder 0 is missing --------------


class _FakeDiscogsNoFolder0:
    """Stand-in DiscogsClient that authenticates but does NOT return folder 0."""

    def __init__(self, _token):
        pass

    def identity(self):
        return {"username": "tester"}

    def folders(self, _username):
        # Folder 0 is absent — the API does not always include it.
        return [
            {"id": 1, "name": "Uncategorized", "count": 0},
            {"id": 10, "name": "jazz", "count": 1},
        ]


class _FakeDiscogsWithFolder0:
    """Stand-in DiscogsClient that includes folder 0 in its folder list."""

    def __init__(self, _token):
        pass

    def identity(self):
        return {"username": "tester"}

    def folders(self, _username):
        return [
            {"id": 0, "name": "All", "count": 42},
            {"id": 1, "name": "Uncategorized", "count": 3},
        ]


def _no_openrouter_secrets():
    """No openrouter_key → cmd_auth skips the AI ping entirely."""
    return {"discogs_pat": "fake-pat"}


def test_cmd_auth_skips_with_warning_when_folder_0_missing(monkeypatch, capsys):
    """A2.5: cmd_auth must not crash with StopIteration when folder 0 is
    absent; it should print a clear warning and continue."""
    monkeypatch.setattr(cli.config, "load_secrets", _no_openrouter_secrets)
    monkeypatch.setattr("lib.discogs.DiscogsClient", _FakeDiscogsNoFolder0)
    monkeypatch.setattr("lib.printer.discover", lambda: [])

    args = argparse.Namespace()
    rc = cli.cmd_auth(args)

    captured = capsys.readouterr()
    # Warning, not crash; exit code 0 (no DiscogsError happened).
    assert rc == 0
    assert "folder 0" in captured.out.lower()
    assert "skipping" in captured.out.lower()
    # The old crash line that used to read "X records" must NOT appear.
    assert "records)" not in captured.out


def test_cmd_auth_prints_count_when_folder_0_present(monkeypatch, capsys):
    """A2.5: when folder 0 IS present, the original 'authenticated as
    <user> (N records)' line must still be printed."""
    monkeypatch.setattr(cli.config, "load_secrets", _no_openrouter_secrets)
    monkeypatch.setattr("lib.discogs.DiscogsClient", _FakeDiscogsWithFolder0)
    monkeypatch.setattr("lib.printer.discover", lambda: [])

    args = argparse.Namespace()
    rc = cli.cmd_auth(args)

    captured = capsys.readouterr()
    assert rc == 0
    assert "42 records" in captured.out
    assert "authenticated as tester" in captured.out


# -- A2.6: cmd_classify --apply must exit cleanly if username is unset ------


def _secrets_with_openrouter():
    return {"discogs_pat": "fake-pat", "openrouter_key": "fake-key"}


def test_cmd_classify_apply_without_username_exits_with_clear_error(conn, monkeypatch):
    """A2.6: when --apply is set but no username has been recorded by a
    prior `records sync`, cmd_classify must exit with a clear message
    BEFORE attempting any Discogs write. Matches the cmd_summarize
    pattern at lib/cli.py:80-82."""
    # conn fixture has no 'username' row in settings → db.get_setting returns None.
    monkeypatch.setattr(cli.config, "load_secrets", _secrets_with_openrouter)

    args = argparse.Namespace(apply=True, review=None, limit=20)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_classify(args)
    # Matches the cmd_summarize error message verbatim so users see a
    # single, consistent hint.
    assert "run `records sync` first" in str(exc.value)


def test_cmd_classify_without_apply_does_not_require_username(conn, monkeypatch):
    """A2.6: the guard is scoped to --apply. A plain `records classify`
    (no --apply) must NOT exit just because there's no stored username
    — it only suggests folders and does not touch Discogs."""
    monkeypatch.setattr(cli.config, "load_secrets", _secrets_with_openrouter)

    # AI client is not invoked here either: no rows in the Uncategorized
    # folder means cmd_classify prints a header and returns 0.
    args = argparse.Namespace(apply=False, review=None, limit=20)
    rc = cli.cmd_classify(args)
    assert rc == 0


# -- A4.3: --limit must be positive and bounded ------------------------------


@pytest.mark.parametrize("bad_limit", [0, -1, -1000])
def test_cmd_summarize_rejects_non_positive_limit(monkeypatch, bad_limit):
    """A4.3: argparse ``type=int`` only validates parseability. ``--limit 0``
    and negative values must exit with a clear error before any AI/DB
    work happens."""
    monkeypatch.setattr(cli.config, "load_secrets", _secrets_with_openrouter)
    args = argparse.Namespace(missing=False, write=False, limit=bad_limit)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_summarize(args)
    assert "--limit must be a positive integer" in str(exc.value)


@pytest.mark.parametrize("bad_limit", [0, -1, -1000])
def test_cmd_classify_rejects_non_positive_limit(monkeypatch, bad_limit):
    """A4.3: same guard applies to ``records classify``."""
    monkeypatch.setattr(cli.config, "load_secrets", _secrets_with_openrouter)
    args = argparse.Namespace(apply=False, review=None, limit=bad_limit)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_classify(args)
    assert "--limit must be a positive integer" in str(exc.value)


def test_cmd_summarize_rejects_oversized_limit(monkeypatch):
    """A4.3: cap --limit at cli.MAX_LIMIT so a fat-fingered 999999 cannot
    stall the CLI for hours. The check happens before any AI/DB call."""
    monkeypatch.setattr(cli.config, "load_secrets", _secrets_with_openrouter)
    args = argparse.Namespace(missing=False, write=False, limit=cli.MAX_LIMIT + 1)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_summarize(args)
    assert f"--limit must be at most {cli.MAX_LIMIT}" in str(exc.value)


def test_cmd_classify_rejects_oversized_limit(monkeypatch):
    """A4.3: same upper bound applies to ``records classify``."""
    monkeypatch.setattr(cli.config, "load_secrets", _secrets_with_openrouter)
    args = argparse.Namespace(apply=False, review=None, limit=cli.MAX_LIMIT + 1)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_classify(args)
    assert f"--limit must be at most {cli.MAX_LIMIT}" in str(exc.value)


# -- A4.5: cmd_restore input validation --------------------------------------


def _write_backup(path, **overrides):
    """Produce a minimal valid backup file payload."""
    payload = {
        "exported_at": "2024-01-01T00:00:00+00:00",
        "purchases": {},
        "folder_colors": {},
        "year_overrides": {},
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload))
    return payload


def test_cmd_restore_exits_when_file_missing(tmp_path):
    """A4.5: a missing backup file is a hard error, not a stack trace."""
    args = argparse.Namespace(file=str(tmp_path / "does-not-exist.json"))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "file not found" in str(exc.value)


def test_cmd_restore_exits_when_file_empty(tmp_path):
    """A4.5: an empty file is rejected before json.load() raises."""
    path = tmp_path / "empty.json"
    path.write_text("")
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "empty" in str(exc.value)


def test_cmd_restore_exits_on_invalid_json(tmp_path):
    """A4.5: garbage in the backup file produces a clear error."""
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "cannot read JSON" in str(exc.value)


def test_cmd_restore_exits_when_top_level_not_object(tmp_path):
    """A4.5: a JSON array or scalar at the top level is rejected before
    any DB write. Without this guard ``.get("purchases")`` would raise
    AttributeError deep in the write loop."""
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]")
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "top-level JSON must be an object" in str(exc.value)


def test_cmd_restore_exits_when_required_keys_missing(tmp_path):
    """A4.5: a backup missing one of the four top-level keys is rejected
    with a list of the missing keys."""
    path = tmp_path / "thin.json"
    path.write_text(json.dumps({"exported_at": "x", "purchases": {}}))
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    msg = str(exc.value)
    assert "missing required keys" in msg
    assert "folder_colors" in msg
    assert "year_overrides" in msg


def test_cmd_restore_exits_on_non_int_instance_id(tmp_path, seeded):
    """A4.5: a non-numeric instance_id key in ``purchases`` is rejected
    before any DB write."""
    path = tmp_path / "bad.json"
    _write_backup(path, purchases={"not-an-int": 1.0})
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "not an int" in str(exc.value)
    # Nothing was written.
    assert seeded.execute("SELECT count(*) FROM purchases").fetchone()[0] == 0


def test_cmd_restore_exits_on_unknown_instance_id(tmp_path, seeded):
    """A4.5: an instance_id that doesn't exist in ``items`` is rejected
    so we never insert an orphan purchase row."""
    path = tmp_path / "bad.json"
    _write_backup(path, purchases={"99999": 1.0})
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "unknown instance_id" in str(exc.value)
    assert seeded.execute("SELECT count(*) FROM purchases").fetchone()[0] == 0


def test_cmd_restore_exits_on_out_of_range_price(tmp_path, seeded):
    """A4.5: a negative or absurdly large paid price is rejected (same
    bound as ``api_paid``)."""
    path_neg = tmp_path / "neg.json"
    _write_backup(path_neg, purchases={"100": -1.0})
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(argparse.Namespace(file=str(path_neg)))
    assert "out of range" in str(exc.value)

    path_big = tmp_path / "big.json"
    _write_backup(path_big, purchases={"100": 1_000_000.01})
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(argparse.Namespace(file=str(path_big)))
    assert "out of range" in str(exc.value)


def test_cmd_restore_exits_on_unknown_folder_id(tmp_path, seeded):
    """A4.5: a folder_id in ``folder_colors`` that doesn't exist is
    rejected so we never run an UPDATE that silently affects 0 rows."""
    path = tmp_path / "bad.json"
    _write_backup(path, folder_colors={"99999": "#abcdef"})
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "unknown folder_id" in str(exc.value)


def test_cmd_restore_exits_on_invalid_year(tmp_path, seeded):
    """A4.5: a year outside 1..9999 is rejected (matches ``api_year``)."""
    path = tmp_path / "bad.json"
    _write_backup(path, year_overrides={"100": 10000})
    args = argparse.Namespace(file=str(path))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_restore(args)
    assert "out of range" in str(exc.value)


def test_cmd_restore_happy_path_restores_all_three_categories(tmp_path, seeded):
    """A4.5: a fully-valid backup file restores all three categories
    successfully and leaves the DB in the expected state."""
    path = tmp_path / "good.json"
    _write_backup(
        path,
        purchases={"100": 12.50},
        folder_colors={"10": "#d0e6f2"},
        year_overrides={"100": 1958},
    )
    args = argparse.Namespace(file=str(path))
    rc = cli.cmd_restore(args)
    assert rc == 0
    assert seeded.execute("SELECT paid_price FROM purchases WHERE instance_id = 100").fetchone()[0] == 12.5
    assert seeded.execute("SELECT color FROM folders WHERE id = 10").fetchone()[0] == "#d0e6f2"
    assert seeded.execute("SELECT year FROM year_overrides WHERE instance_id = 100").fetchone()[0] == 1958
