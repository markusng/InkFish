"""Per-file layout persistence — zoom, scroll position, sub-window geometry."""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path.home() / ".config" / "inkfish" / "layouts.json"


def load_layouts() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_layouts(data: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_layout(path: Path) -> dict | None:
    return load_layouts().get(str(path.resolve()))


def set_layout(path: Path, data: dict) -> None:
    all_layouts = load_layouts()
    all_layouts[str(path.resolve())] = data
    save_layouts(all_layouts)
