"""Tests for CLI command guards (A2.5, A2.6)."""

import argparse

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
