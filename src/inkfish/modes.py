"""Source/Rendered mode toggle for `.md` and `.html`."""
from __future__ import annotations

from enum import Enum
from typing import Protocol


class _DocSink(Protocol):
    def set_text(self, text: str) -> None: ...
    def set_markdown(self, text: str) -> None: ...
    def set_html(self, text: str) -> None: ...


class Mode(Enum):
    SOURCE = "source"
    RENDERED = "rendered"


_TOGGLEABLE = frozenset({".md", ".html"})


def is_toggleable(ext: str) -> bool:
    return ext.lower() in _TOGGLEABLE


def apply_mode(item: _DocSink, raw_text: str, ext: str, mode: Mode) -> None:
    ext = ext.lower()
    if mode is Mode.RENDERED and ext == ".md":
        item.set_markdown(raw_text)
    elif mode is Mode.RENDERED and ext == ".html":
        item.set_html(raw_text)
    else:
        item.set_text(raw_text)
