# Contributing

Bug reports, protocol captures from other desk controllers and pull requests are all welcome. The
full guide is [CONTRIBUTING.md](https://github.com/j0rdsta/ha-desky/blob/main/CONTRIBUTING.md) in
the repository; this page is a summary.

## Reporting a problem

[Open an issue](https://github.com/j0rdsta/ha-desky/issues) with what you expected, what
happened, your Home Assistant version, and a [debug log](troubleshooting.md#debug-logging). If the
desk sends frames the integration does not recognise, include the `Received notification:` lines.

## Development setup

The latest stable Home Assistant needs Python 3.14. The minimum supported release, 2025.10, needs
Python 3.13.

```bash
git clone https://github.com/j0rdsta/ha-desky.git
cd ha-desky
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt    # or requirements_test_min.txt on Python 3.13
pip install -r <(python script/ha_test_requirements.py)
pre-commit install
```

## Checks

```bash
pre-commit run --all-files   # ruff, ruff format, mypy and file hygiene
pytest --cov                 # tests with coverage
```

Tests mock the Bluetooth traffic, so no desk is needed. New behaviour needs tests, and a bug fix
needs a test that fails without it.

## Documentation

This site is built with [MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) from the `docs/` folder.

```bash
pip install -r requirements_docs.txt
mkdocs serve                 # preview at http://127.0.0.1:8000
mkdocs build --strict        # the check CI runs, which fails on broken links
```

## Pull requests

- Every change lands on `main` through a pull request with green checks.
- Use a [Conventional Commit](https://www.conventionalcommits.org/) title, such as
  `fix: keep the height updating after a reconnect`. Pull requests are squash-merged, so the
  title becomes the commit and the changelog entry.
- Entity unique IDs and entity IDs never change for existing users. A breaking change needs a
  migration and a release note.

## Testing on a real desk

A standing desk is motorised furniture. Keep the area above and below it clear, stay within reach
of the hand controller, and try presets and height commands with small movements first.
