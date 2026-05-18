"""EditorSubWindow — QMdiSubWindow wrapping an EditorPane."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMdiSubWindow

from .editor_pane import EditorPane
from . import layouts


class EditorSubWindow(QMdiSubWindow):
    def __init__(self, pane: EditorPane) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWidget(pane)
        self.resize(680, 500)
        pane.title_changed.connect(self.setWindowTitle)
        pane.close_requested.connect(self.close)
        self.setWindowTitle(pane.display_name())

    @property
    def pane(self) -> EditorPane:
        return self.widget()

    def closeEvent(self, event: QCloseEvent) -> None:
        pane = self.pane
        if not pane.confirm_discard():
            event.ignore()
            return
        path = pane.current_path
        if path is not None:
            data = pane.capture_layout()
            geo = self.geometry()
            data["geometry"] = [geo.x(), geo.y(), geo.width(), geo.height()]
            layouts.set_layout(path, data)
        super().closeEvent(event)
