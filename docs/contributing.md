# Contributing

Bug reports, protocol captures from other desk controllers and pull requests are all welcome.
Development setup, checks, pull request rules and the release process are in
[CONTRIBUTING.md](https://github.com/j0rdsta/ha-desky/blob/main/CONTRIBUTING.md) in the
repository.

## Reporting a problem

[Open an issue](https://github.com/j0rdsta/ha-desky/issues) with what you expected, what
happened, your Home Assistant version, and a [debug log](troubleshooting.md#debug-logging). If the
desk sends frames the integration does not recognise, include the `Received notification:` lines.

## Documentation

This site is built with [MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) from the `docs/` folder.

```bash
pip install -r requirements_docs.txt
mkdocs serve                 # preview at http://127.0.0.1:8000
mkdocs build --strict        # the check CI runs, which fails on broken links
```
