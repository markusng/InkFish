"""EditorPane — self-contained per-document editor widget."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QTransform
from PyQt6.QtWidgets import (
    QFileDialog, QInputDialog, QMessageBox, QVBoxLayout, QWidget,
)

from .canvas import InkfishView
from .io import file_dialog_filter, load_file, save_file
from .modes import Mode, apply_mode, is_toggleable


class EditorPane(QWidget):
    """Owns a single document: InkfishView, text state, vim engine."""

    title_changed        = pyqtSignal(str)   # "name[*]" or "untitled[*]"
    zoom_changed         = pyqtSignal(float)
    vim_mode_changed     = pyqtSignal(str)   # VimMode name
    command_buf_changed  = pyqtSignal(str)
    mode_label_changed   = pyqtSignal(str)   # "SOURCE" / "RENDERED"
    vim_toggled          = pyqtSignal(bool)  # True = vim on
    line_numbers_toggled = pyqtSignal(bool)  # True = visible
    close_requested      = pyqtSignal()      # triggered by vim :q / :wq

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = InkfishView(self)
        layout.addWidget(self._view)
        self._doc_item = self._view.document_item

        self._current_path: Path | None = None
        self._raw_text: str = ""
        self._mode: Mode = Mode.SOURCE
        self._suppress_dirty = False
        self._vim_engine = None

        self._doc_item.document().modificationChanged.connect(self._on_modification_changed)
        self._view.zoom_changed.connect(self.zoom_changed)
        self._doc_item.vim_mode_changed.connect(self.vim_mode_changed)
        self._doc_item.command_buf_changed.connect(self.command_buf_changed)
        self._doc_item.scroll_half_page.connect(self._view.scroll_half_page)
        self._doc_item.scroll_page.connect(self._view.scroll_page)
        self._doc_item.search_requested.connect(self._on_search_requested)
        self._doc_item.search_next_signal.connect(self._on_search_next)
        self._doc_item.ex_command.connect(self._on_ex_command)

    # ---- public accessors -----------------------------------------------------

    @property
    def view(self) -> InkfishView:
        return self._view

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def is_modified(self) -> bool:
        return self._doc_item.document().isModified()

    def display_name(self) -> str:
        name = self._current_path.name if self._current_path else "untitled"
        dirty = "*" if self.is_modified() else ""
        return f"{name}{dirty}"

    def mode_label(self) -> str:
        ext = self._current_ext()
        return self._mode.name if is_toggleable(ext) else "SOURCE"

    def vim_enabled(self) -> bool:
        return self._vim_engine is not None

    # ---- file ops -------------------------------------------------------------

    def open_path(self, path: Path) -> None:
        text, _ = load_file(path)
        self._current_path = path
        self._raw_text = text
        self._mode = Mode.SOURCE
        self._apply_current_mode()
        self._doc_item.document().setModified(False)
        self._view.scroll_to_document_origin()
        self._emit_title()
        self.mode_label_changed.emit(self.mode_label())

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
        self._emit_title()
        return True

    # ---- view ops -------------------------------------------------------------

    def reset_view(self) -> None:
        self._view.reset_view()

    def center_on_cursor(self) -> None:
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

    def capture_layout(self) -> dict:
        return {
            "zoom": self._view.current_scale(),
            "scroll_x": self._view.horizontalScrollBar().value(),
            "scroll_y": self._view.verticalScrollBar().value(),
        }

    def apply_layout(self, zoom: float, scroll_x: int, scroll_y: int) -> None:
        self._view.setTransform(QTransform())
        zoom = max(0.01, min(1000.0, zoom))
        self._view.scale(zoom, zoom)
        self._view.zoom_changed.emit(zoom)

        def _restore_scroll() -> None:
            self._view.horizontalScrollBar().setValue(scroll_x)
            self._view.verticalScrollBar().setValue(scroll_y)

        QTimer.singleShot(0, _restore_scroll)

    # ---- mode / folding -------------------------------------------------------

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
        self.mode_label_changed.emit(self.mode_label())

    def toggle_fold_at_cursor(self) -> None:
        self._doc_item.toggle_fold_at_cursor(self._current_ext())

    def _apply_current_mode(self) -> None:
        self._suppress_dirty = True
        try:
            apply_mode(self._doc_item, self._raw_text, self._current_ext(), self._mode)
            self._doc_item.set_editable(self._mode is Mode.SOURCE)
        finally:
            self._suppress_dirty = False
        self._doc_item.document().setModified(False)

    # ---- vim mode -------------------------------------------------------------

    def toggle_vim(self) -> None:
        from .vim import VimEngine
        if self._vim_engine is None:
            self._vim_engine = VimEngine()
            self._doc_item.set_vim(self._vim_engine)
            self.vim_toggled.emit(True)
        else:
            self._vim_engine = None
            self._doc_item.set_vim(None)
            self.vim_toggled.emit(False)

    def toggle_line_numbers(self) -> None:
        visible = not self._view.line_numbers_visible()
        self._view.set_line_numbers_visible(visible)
        self.line_numbers_toggled.emit(visible)

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._view.set_line_numbers_visible(visible)
        self.line_numbers_toggled.emit(visible)

    def line_numbers_visible(self) -> bool:
        return self._view.line_numbers_visible()

    def set_vim_enabled(self, enabled: bool) -> None:
        if enabled and self._vim_engine is None:
            self.toggle_vim()
        elif not enabled and self._vim_engine is not None:
            self.toggle_vim()

    # ---- close ----------------------------------------------------------------

    def confirm_discard(self) -> bool:
        if not self.is_modified():
            return True
        name = self._current_path.name if self._current_path else "untitled"
        choice = QMessageBox.question(
            self,
            "SquidPad",
            f"Save changes to {name}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    # ---- internal slots -------------------------------------------------------

    def _current_ext(self) -> str:
        return self._current_path.suffix.lower() if self._current_path else ".txt"

    def _emit_title(self) -> None:
        self.title_changed.emit(self.display_name())

    def _on_modification_changed(self, _: bool) -> None:
        if not self._suppress_dirty:
            self._emit_title()

    def _on_search_requested(self, pattern: str) -> None:
        if not pattern:
            pattern, ok = QInputDialog.getText(self, "Search", "/")
            if not ok or not pattern:
                return
        self._doc_item.do_search(pattern, forward=True)

    def _on_search_next(self, forward: bool) -> None:
        self._doc_item.do_search("", forward=forward)

    def _on_ex_command(self, cmd: str) -> None:
        cmd = cmd.strip()
        if cmd in ("w", "write"):
            self.save()
        elif cmd in ("q", "quit"):
            self.close_requested.emit()
        elif cmd in ("wq", "x", "write-quit"):
            if self.save():
                self.close_requested.emit()
        elif cmd.startswith(("e ", "edit ")):
            self.open_path(Path(cmd.split(None, 1)[1].strip()))
        elif cmd == "set vim":
            self.set_vim_enabled(True)
        elif cmd == "set novim":
            self.set_vim_enabled(False)
