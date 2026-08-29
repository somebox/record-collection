# Contributing

Thanks for your interest in Record Collection. This is a small personal project
that keeps a physical record collection in sync with
[Discogs](https://www.discogs.com) and prints labels for a Brother QL printer.
Contributions of all sizes are welcome — bug reports, fixes, doc tweaks, and
new features.

## Code of conduct

There isn't a separate Code of Conduct for this project yet. In the meantime,
follow the standard [Contributor Covenant](https://www.contributor-covenant.org/)
spirit: be respectful, assume good faith, and prefer private feedback over
public callouts.

## Reporting issues

- **Bug reports:** open an issue with what you ran, what you expected, and
  what happened. The commit SHA you ran against is helpful.
- **Feature requests:** open an issue with the use case. The project is
  small, so scope creep is a real risk — describe the problem first, the
  solution second.
- **Security:** there is no private disclosure channel yet; open an issue
  and mark it clearly. Don't paste real tokens in public.

## Development setup

The project uses [`uv`](https://docs.astral.sh/uv/) for Python packaging and
dependency management. There is no `package.json`, no Node tooling, no
container setup.

```sh
git clone <repo-url>
cd record-collection
cp secrets.example.yaml secrets.yaml    # fill in your Discogs token
cp settings.example.yaml settings.yaml  # optional; defaults work
uv sync                                 # install Python deps
uv run records auth                     # verify your token
uv run pytest                           # run the test suite
```

The web app starts with `uv run records serve` and binds to
`http://127.0.0.1:5033`.

## Project layout

```
record-collection/
├── lib/                # the application: db, sync, web, cli, labels
│   ├── static/         # CSS, JS, fonts (the frontend)
│   ├── templates/      # Jinja templates
│   ├── cli.py
│   ├── db.py
│   ├── discogs.py
│   ├── ai.py
│   ├── labels.py
│   ├── printer.py
│   ├── sync.py
│   └── web.py
├── tests/              # pytest suite
├── docs/               # see docs/spec.md for the architecture
│   ├── spec.md
│   ├── frontend-styleguide.md
│   ├── api-notes.md
│   ├── dev-plan.md
│   └── images/
├── scripts/            # operator scripts (e.g. cards-board.sh)
├── pyproject.toml      # project metadata + dependencies (uv)
├── secrets.example.yaml
├── settings.example.yaml
├── CHANGELOG.md
└── CONTRIBUTING.md
```

## Conventions

- **Python:** standard library typing; `from __future__ import annotations` at
  the top of every module. Prefer small, single-purpose functions; raise
  specific exceptions, not bare `Exception`.
- **Commits:** the project follows [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`. One concern per
  commit; small commits are fine.
- **Docs:** every doc carries the YAML frontmatter schema
  (`title`, `last_updated`, `status`, `scope`, `audience`, `tags`). Filenames
  are `lowercase-with-dashes.md`; the standard top-level files (`README.md`,
  `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`) are uppercase. See
  [docs/frontend-styleguide.md](docs/frontend-styleguide.md) for the
  frontend conventions; there isn't yet a separate prose-doc style guide.
- **Tests:** every bug fix lands with a regression test. Run `uv run pytest`
  locally before opening a PR.

## Pull requests

- Branch from `main`. Use a descriptive branch name (`fix/discogs-401-retry`,
  `feat/crate-keyboard-nav`).
- Keep PRs small. A 200-line PR is easier to review than a 2,000-line one.
- Reference the issue in the PR description with `Closes #N` or `Refs #N`.
- Make sure `uv run pytest` is green before requesting review.
- Squash-merge is fine; the maintainer will write the final commit message
  if your branch history is messy.

## Releasing

There is no formal release cadence. When a meaningful batch of features lands,
the maintainer cuts a tag, writes a `CHANGELOG.md` entry, and pushes. The
project is currently pre-1.0, so breaking changes are expected and will be
called out in the changelog.
