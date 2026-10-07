"""Print the pinned requirements of the HA components this integration loads in tests.

pytest-homeassistant-custom-component installs Home Assistant core but not the
requirements of individual components. This resolves them from the installed
Home Assistant version, so each CI leg gets the exact pins that version expects.
"""

from __future__ import annotations

import json
from pathlib import Path

import homeassistant.components

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "desky_desk" / "manifest.json"
COMPONENTS = Path(homeassistant.components.__file__).parent


def main() -> None:
    """Print one requirement per line."""
    todo = [*json.loads(MANIFEST.read_text())["dependencies"], "bluetooth"]
    seen: set[str] = set()
    requirements: set[str] = set()
    while todo:
        domain = todo.pop()
        if domain in seen:
            continue
        seen.add(domain)
        manifest = COMPONENTS / domain / "manifest.json"
        if not manifest.exists():
            continue
        data = json.loads(manifest.read_text())
        requirements.update(data.get("requirements", []))
        todo.extend(data.get("dependencies", []))
    print("\n".join(sorted(requirements)))


if __name__ == "__main__":
    main()
