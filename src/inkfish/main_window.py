"""Top-level QMainWindow: hosts the canvas, menus, status bar, hotkeys."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QFileDialog, QInputDialog, QLabel, QMainWindow, QMessageBox,
)

from .canvas import InkfishView
from .hotkeys import register_shortcuts
from .io import file_dialog_filter, load_file, save_file
from .modes import Mode, apply_mode, is_toggleable
from . import settings


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("inkfish")
        self.resize(1000, 720)

        self._view = InkfishView(self)
        self.setCentralWidget(self._view)
        self._doc_item = self._view.document_item

        self._current_path: Path | None = None
        self._raw_text: str = ""
        self._mode: Mode = Mode.SOURCE
        self._suppress_dirty = False
        self._vim_engine = None  # VimEngine | None

        self._build_menus()
        self._build_status_bar()
        register_shortcuts(self)

        self._doc_item.document().modificationChanged.connect(self._on_modification_changed)
        self._view.zoom_changed.connect(self._update_zoom_label)
        self._doc_item.vim_mode_changed.connect(self._on_vim_mode_changed)
        self._doc_item.ex_command.connect(self._on_ex_command)
        self._doc_item.command_buf_changed.connect(self._on_command_buf_changed)
        self._doc_item.scroll_half_page.connect(self._view.scroll_half_page)
        self._doc_item.scroll_page.connect(self._view.scroll_page)
        self._doc_item.search_requested.connect(self._on_search_requested)
        self._doc_item.search_next_signal.connect(self._on_search_next)

        self._update_title()
        self._update_zoom_label(1.0)
        self._update_mode_label()

        # Restore saved preferences
        prefs = settings.load()
        if prefs.get("vim_mode"):
            self.toggle_vim()

    # ---- menus / status bar ---------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self._act_open = QAction("&Open…", self)
        self._act_open.triggered.connect(self.open_file_dialog)
        file_menu.addAction(self._act_open)

        self._act_save = QAction("&Save", self)
        self._act_save.triggered.connect(self.save)
        file_menu.addAction(self._act_save)

        self._act_save_as = QAction("Save &As…", self)
        self._act_save_as.triggered.connect(self.save_as)
        file_menu.addAction(self._act_save_as)

        file_menu.addSeparator()

        self._act_quit = QAction("&Quit", self)
        self._act_quit.triggered.connect(self.close)
        file_menu.addAction(self._act_quit)

        view_menu = self.menuBar().addMenu("&View")

        self._act_toggle_mode = QAction("Toggle &Rendered/Source", self)
        self._act_toggle_mode.triggered.connect(self.toggle_mode)
        view_menu.addAction(self._act_toggle_mode)

        self._act_toggle_fold = QAction("Toggle &Fold at Cursor", self)
        self._act_toggle_fold.triggered.connect(self.toggle_fold_at_cursor)
        view_menu.addAction(self._act_toggle_fold)

        self._act_reset_view = QAction("&Reset Zoom && Pan", self)
        self._act_reset_view.triggered.connect(self.reset_view)
        view_menu.addAction(self._act_reset_view)

        self._act_center_on_cursor = QAction("&Centre on Cursor", self)
        self._act_center_on_cursor.triggered.connect(self.center_on_cursor)
        view_menu.addAction(self._act_center_on_cursor)

        view_menu.addSeparator()

        self._act_vim_mode = QAction("&Vim Mode", self)
        self._act_vim_mode.setCheckable(True)
        self._act_vim_mode.triggered.connect(self.toggle_vim)
        view_menu.addAction(self._act_vim_mode)

    def _build_status_bar(self) -> None:
        self._vim_label = QLabel("")
        self._vim_label.setVisible(False)
        self.statusBar().addWidget(self._vim_label)   # left-aligned

        self._zoom_label = QLabel("100%")
        self._mode_label = QLabel("SOURCE")
        self.statusBar().addPermanentWidget(self._mode_label)
        self.statusBar().addPermanentWidget(self._zoom_label)

    # ---- file ops -------------------------------------------------------------

    def open_path(self, path: Path) -> None:
        if not self._confirm_discard_changes():
            return
        text, ext = load_file(path)
        self._current_path = path
        self._raw_text = text
        self._mode = Mode.SOURCE
        self._apply_current_mode()
        self._doc_item.document().setModified(False)
        self._update_title()
        self._update_mode_label()
        self._view.scroll_to_document_origin()

    def open_file_dialog(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open file", "", file_dialog_filter()
        )
        if path_str:
            self.open_path(Path(path_str))

    def save(self) -> bool:
        if self._current_path is None:
            return self.save_as()
        return self._save_to(self._current_path)

    def save_as(self) -> bool:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save file as", "", file_dialog_filter()
        )
        if not path_str:
            return False
        return self._save_to(Path(path_str))

    def _save_to(self, path: Path) -> bool:
        text = self._raw_text if self._mode is Mode.RENDERED else self._doc_item.text()
        save_file(path, text)
        self._current_path = path
        self._raw_text = text
        self._doc_item.document().setModified(False)
        self._update_title()
        return True

    # ---- view ops ------------------------------------------------------------

    def reset_view(self) -> None:
        self._view.reset_view()

    def center_on_cursor(self) -> None:
        from PyQt6.QtCore import QPointF
        cursor = self._doc_item.textCursor()
        block = cursor.block()
        block_rect = self._doc_item.document().documentLayout().blockBoundingRect(block)
        block_layout = block.layout()
        x, y = block_rect.x(), block_rect.y()
        if block_layout:
            line = block_layout.lineForTextPosition(cursor.positionInBlock())
            if line.isValid():
                cursor_x, _ = line.cursorToX(cursor.positionInBlock())
                x = block_rect.x() + cursor_x
                y = block_rect.y() + line.y()
        scene_pos = self._doc_item.mapToScene(QPointF(x, y))
        self._view.centerOn(scene_pos)

    # ---- mode toggle / folding -----------------------------------------------

    def toggle_mode(self) -> None:
        ext = self._current_ext()
        if not is_toggleable(ext):
            return
        if self._mode is Mode.SOURCE:
            self._raw_text = self._doc_item.text()
            self._mode = Mode.RENDERED
        else:
            self._mode = Mode.SOURCE
        self._apply_current_mode()
        self._update_mode_label()

    def toggle_fold_at_cursor(self) -> None:
        ext = self._current_ext()
        self._doc_item.toggle_fold_at_cursor(ext)

    def _apply_current_mode(self) -> None:
        self._suppress_dirty = True
        try:
            apply_mode(self._doc_item, self._raw_text, self._current_ext(), self._mode)
            self._doc_item.set_editable(self._mode is Mode.SOURCE)
        finally:
            self._suppress_dirty = False
        self._doc_item.document().setModified(False)

    # ---- Vim mode ------------------------------------------------------------

    def toggle_vim(self) -> None:
        from .vim import VimEngine
        if self._vim_engine is None:
            self._vim_engine = VimEngine()
            self._doc_item.set_vim(self._vim_engine)
            self._act_vim_mode.setChecked(True)
            self._vim_label.setText("-- NORMAL --")
            self._vim_label.setVisible(True)
            settings.save({**settings.load(), "vim_mode": True})
        else:
            self._vim_engine = None
            self._doc_item.set_vim(None)
            self._act_vim_mode.setChecked(False)
            self._vim_label.setVisible(False)
            settings.save({**settings.load(), "vim_mode": False})

    def _on_vim_mode_changed(self, mode_name: str) -> None:
        labels = {
            "NORMAL":      "-- NORMAL --",
            "INSERT":      "-- INSERT --",
            "VISUAL":      "-- VISUAL --",
            "VISUAL_LINE": "-- VISUAL LINE --",
            "COMMAND":     "",
        }
        self._vim_label.setText(labels.get(mode_name, f"-- {mode_name} --"))

    def _on_command_buf_changed(self, buf: str) -> None:
        self._vim_label.setText(buf)

    def _on_ex_command(self, cmd: str) -> None:
        cmd = cmd.strip()
        if cmd in ("w", "write"):
            self.save()
        elif cmd in ("q", "quit"):
            self.close()
        elif cmd in ("wq", "x", "write-quit"):
            if self.save():
                self.close()
        elif cmd.startswith(("e ", "edit ")):
            path_str = cmd.split(None, 1)[1].strip()
            self.open_path(Path(path_str))
        elif cmd == "set vim":
            if not self._vim_engine:
                self.toggle_vim()
        elif cmd == "set novim":
            if self._vim_engine:
                self.toggle_vim()

    def _on_search_requested(self, pattern: str) -> None:
        if not pattern:
            pattern, ok = QInputDialog.getText(self, "Search", "/")
            if not ok or not pattern:
                return
        self._doc_item.do_search(pattern, forward=True)

    def _on_search_next(self, forward: bool) -> None:
        self._doc_item.do_search("", forward=forward)

    # ---- helpers --------------------------------------------------------------

    def _current_ext(self) -> str:
        return self._current_path.suffix.lower() if self._current_path else ".txt"

    def _on_modification_changed(self, modified: bool) -> None:
        if self._suppress_dirty:
            return
        self._update_title()

    def _update_title(self) -> None:
        name = self._current_path.name if self._current_path else "untitled"
        dirty = "*" if self._doc_item.document().isModified() else ""
        self.setWindowTitle(f"inkfish — {name}{dirty}")

    def _update_zoom_label(self, factor: float) -> None:
        self._zoom_label.setText(f"{int(round(factor * 100))}%")

    def _update_mode_label(self) -> None:
        ext = self._current_ext()
        label = self._mode.name if is_toggleable(ext) else "SOURCE"
        self._mode_label.setText(label)

    def _confirm_discard_changes(self) -> bool:
        if not self._doc_item.document().isModified():
            return True
        choice = QMessageBox.question(
            self,
            "inkfish",
            "Discard unsaved changes?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        if choice == QMessageBox.StandardButton.Discard:
            return True
        return False

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()
