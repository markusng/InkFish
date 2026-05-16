"""File I/O — open/save for the three supported extensions."""
from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTS = frozenset({".txt", ".md", ".html"})


def load_file(path: Path) -> tuple[str, str]:
    """Return ``(raw_text, ext)`` for *path*.

    Raises ``ValueError`` for unsupported extensions and ``FileNotFoundError``
    if the file is missing.
    """
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type: {ext or '(no extension)'}")
    text = path.read_text(encoding="utf-8")
    return text, ext


def save_file(path: Path, text: str) -> None:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type: {ext or '(no extension)'}")
    path.write_text(text, encoding="utf-8")


def file_dialog_filter() -> str:
    return "Text files (*.txt *.md *.html);;All files (*)"
