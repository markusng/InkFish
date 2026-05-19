"""Central hotkey registry — single binding table for the whole app."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QKeySequence

if TYPE_CHECKING:
    from .main_window import MainWindow


def register_shortcuts(window: "MainWindow") -> None:
    window._act_open.setShortcut(QKeySequence.StandardKey.Open)
    window._act_save.setShortcut(QKeySequence.StandardKey.Save)
    window._act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
    window._act_quit.setShortcut(QKeySequence.StandardKey.Quit)
    window._act_toggle_mode.setShortcut(QKeySequence("Ctrl+E"))
    window._act_toggle_fold.setShortcut(QKeySequence("Ctrl+."))
    window._act_reset_view.setShortcut(QKeySequence("Ctrl+R"))
    window._act_vim_mode.setShortcut(QKeySequence("Ctrl+Shift+V"))
    window._act_center_on_cursor.setShortcut(QKeySequence("Ctrl+G"))
    window._act_fit_page.setShortcut(QKeySequence("Ctrl+J"))
    window._act_find_replace.setShortcut(QKeySequence("Ctrl+H"))
    window._act_line_numbers.setShortcut(QKeySequence("Ctrl+L"))
    window._act_new_editor.setShortcut(QKeySequence("Ctrl+N"))
    window._act_close_editor.setShortcut(QKeySequence("Ctrl+W"))
    window._act_toggle_mdi_mode.setShortcut(QKeySequence("Ctrl+Shift+M"))
