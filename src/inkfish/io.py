"""File I/O — open/save for supported extensions."""
from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTS = frozenset({
    ".txt", ".md", ".html",
    ".py", ".c", ".cpp", ".h", ".c++", ".h++", ".js",
})


def load_file(path: Path) -> tuple[str, str]:
    """Return ``(raw_text, ext)`` for *path*.

    Unknown extensions are treated as plain text and reported as ``.txt``.
    Raises ``FileNotFoundError`` if the file is missing.
    """
    ext = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    return text, ext if ext in SUPPORTED_EXTS else ".txt"


def save_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def file_dialog_filter() -> str:
    return (
        "Text files (*.txt *.md *.html);;"
        "Code files (*.py *.c *.cpp *.h *.js);;"
        "All files (*)"
    )
