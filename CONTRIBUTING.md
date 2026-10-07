# Contributing

Thanks for helping improve the Desky Standing Desk integration. Bug reports, protocol captures
from other desk controllers and pull requests are all welcome.

## Development setup

The latest stable Home Assistant needs Python 3.14. The minimum supported release (2025.10)
needs Python 3.13.

```bash
git clone https://github.com/j0rdsta/ha-desky.git
cd ha-desky
python3.14 -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements_test.txt    # or requirements_test_min.txt on Python 3.13
pip install -r <(python script/ha_test_requirements.py)
pre-commit install
```

`script/ha_test_requirements.py` prints the pinned requirements of the Home Assistant components
this integration loads (Bluetooth and its dependencies) for the installed Home Assistant version.

## Checks

```bash
pre-commit run --all-files   # ruff, ruff-format, mypy and file hygiene
pytest --cov                 # tests with coverage
```

CI runs the same checks on every pull request:

| Workflow | What it runs |
| --- | --- |
| [Lint](.github/workflows/lint.yml) | ruff check, ruff format, mypy |
| [Test](.github/workflows/test.yml) | pytest on Home Assistant 2025.10 and the latest stable release, plus a non-blocking beta job |
| [Validate](.github/workflows/validate.yml) | hassfest and the HACS action |
| [PR title](.github/workflows/pr-title.yml) | Conventional Commit PR title |

## Tests

Tests live in [`tests/`](tests/) and use
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).
BLE traffic is mocked, so no desk is needed. New behaviour needs tests; bug fixes should include a
test that fails without the fix.

## Pull requests

- `main` is protected. Every change lands through a pull request with green checks.
- Use a [Conventional Commit](https://www.conventionalcommits.org/) PR title, for example
  `fix: keep height sensor updating after reconnect` or `feat: add standing time sensor`.
  PRs are squash-merged, so the title becomes the commit message on `main` and the changelog
  entry. Individual commits inside a PR do not need any particular format.
- Reference the issue the PR closes (`Closes #12`).
- Entity unique IDs and entity IDs must never change for existing users. A breaking change needs
  a migration and a release note.

## Hardware notes

A standing desk is motorised furniture. When testing movement on a real desk:

- Keep the area above and below the desk clear, and stay within reach of the desk's own controls.
- Test presets and height commands with small movements first.
- Desk firmware differs between controllers. If you see notifications the integration does not
  recognise, enable debug logging (see the [README](README.md#troubleshooting)) and include the
  `Received notification:` lines in your issue or PR.

## Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please):

1. Merged `feat:` and `fix:` commits (and other user-facing types) are collected into a release
   pull request titled `chore(main): release X.Y.Z`.
2. That PR bumps `version` in `custom_components/desky_desk/manifest.json`, updates
   `.release-please-manifest.json` and adds the changes to `CHANGELOG.md`. It stays open and
   updates itself as more changes merge.
3. Merging the release PR tags `vX.Y.Z` and publishes the GitHub release that HACS installs.

`feat:` bumps the minor version, `fix:` the patch version, and a `!` or `BREAKING CHANGE:` footer
the major version.
