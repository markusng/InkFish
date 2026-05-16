"""Top-level QMainWindow: hosts the canvas, menus, status bar, hotkeys."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from .canvas import InkfishView
from .hotkeys import register_shortcuts
from .io import SUPPORTED_EXTS, file_dialog_filter, load_file, save_file
from .modes import Mode, apply_mode, is_toggleable


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

        self._build_menus()
        self._build_status_bar()
        register_shortcuts(self)

        self._doc_item.document().modificationChanged.connect(self._on_modification_changed)
        self._view.zoom_changed.connect(self._update_zoom_label)
        self._update_title()
        self._update_zoom_label(1.0)
        self._update_mode_label()

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

    def _build_status_bar(self) -> None:
        from PyQt6.QtWidgets import QLabel

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
        if path.suffix.lower() not in SUPPORTED_EXTS:
            QMessageBox.warning(self, "inkfish", f"Unsupported file type: {path.suffix}")
            return False
        text = self._raw_text if self._mode is Mode.RENDERED else self._doc_item.text()
        save_file(path, text)
        self._current_path = path
        self._raw_text = text
        self._doc_item.document().setModified(False)
        self._update_title()
        return True

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
