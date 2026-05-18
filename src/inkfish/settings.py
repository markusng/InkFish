"""Persistent user settings — stored as JSON at ~/.config/inkfish/settings.json."""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path.home() / ".config" / "inkfish" / "settings.json"


def load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save(data: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
